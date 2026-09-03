import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { registerHooks, stripTypeScriptTypes } from 'node:module'
import path from 'node:path'
import { test } from 'node:test'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith('.') && context.parentURL?.startsWith('file:')) {
      const candidate = path.resolve(path.dirname(fileURLToPath(context.parentURL)), specifier)
      for (const resolvedPath of [candidate, `${candidate}.ts`]) {
        if (existsSync(resolvedPath)) {
          return { url: pathToFileURL(resolvedPath).href, shortCircuit: true }
        }
      }
    }
    return nextResolve(specifier, context)
  },
  load(url, context, nextLoad) {
    if (url.endsWith('.ts')) {
      return {
        format: 'module',
        source: stripTypeScriptTypes(readFileSync(fileURLToPath(url), 'utf8'), { mode: 'strip' }),
        shortCircuit: true,
      }
    }
    return nextLoad(url, context)
  },
})

const {
  createApiRestartRecoveryRunCoordinator,
  orchestrateApiRestartRecovery,
} = await import('../lib/api/restart-orchestration.ts')

const noDelay = async () => {}

test('a changed process identity proves recovery without observing a fast outage', async () => {
  const observations = [
    { status: 'ok', instance_id: 'old-process' },
    { status: 'ok', instance_id: 'new-process' },
  ]
  const order = []
  const outcome = await orchestrateApiRestartRecovery({
    baselineInstanceId: 'old-process',
    probe: async () => {
      const health = observations.shift()
      order.push(`probe:${health.instance_id}`)
      return health
    },
    refreshActiveData: async () => order.push('refresh'),
    signal: new AbortController().signal,
    intervalMs: 0,
    maxAttempts: 2,
    delay: noDelay,
  })

  assert.deepEqual(outcome, { status: 'recovered', outageObserved: false })
  assert.deepEqual(order, ['probe:old-process', 'probe:new-process', 'refresh'])
})

test('the accepting process identity cannot recover until it changes', async () => {
  let refreshes = 0
  const outcome = await orchestrateApiRestartRecovery({
    baselineInstanceId: 'same-process',
    probe: async () => ({ status: 'ok', instance_id: 'same-process' }),
    refreshActiveData: async () => {
      refreshes += 1
    },
    signal: new AbortController().signal,
    intervalMs: 0,
    maxAttempts: 3,
    delay: noDelay,
  })

  assert.deepEqual(outcome, { status: 'timeout', outageObserved: false })
  assert.equal(refreshes, 0)
})

test('older APIs recover only after the fallback observes an outage', async () => {
  const observations = [new Error('offline'), { status: 'ok' }]
  const order = []
  const outcome = await orchestrateApiRestartRecovery({
    probe: async () => {
      const observation = observations.shift()
      if (observation instanceof Error) {
        order.push('probe:offline')
        throw observation
      }
      order.push('probe:legacy-ok')
      return observation
    },
    refreshActiveData: async () => order.push('refresh'),
    signal: new AbortController().signal,
    intervalMs: 0,
    maxAttempts: 2,
    delay: noDelay,
  })

  assert.deepEqual(outcome, { status: 'recovered', outageObserved: true })
  assert.deepEqual(order, ['probe:offline', 'probe:legacy-ok', 'refresh'])
})

test('a retry can retain a previously observed legacy outage', async () => {
  let refreshes = 0
  const outcome = await orchestrateApiRestartRecovery({
    initialOutageObserved: true,
    probe: async () => ({ status: 'ok' }),
    refreshActiveData: async () => {
      refreshes += 1
    },
    signal: new AbortController().signal,
    maxAttempts: 1,
    delay: noDelay,
  })

  assert.deepEqual(outcome, { status: 'recovered', outageObserved: true })
  assert.equal(refreshes, 1)
})

test('refresh errors propagate so UI cleanup can run in finally', async () => {
  const failure = new Error('refetch failed')
  await assert.rejects(
    orchestrateApiRestartRecovery({
      baselineInstanceId: 'old-process',
      probe: async () => ({ status: 'ok', instance_id: 'new-process' }),
      refreshActiveData: async () => {
        throw failure
      },
      signal: new AbortController().signal,
      maxAttempts: 1,
      delay: noDelay,
    }),
    failure,
  )
})

test('run tokens are unique and a remount cancels but cannot clear the newer run', () => {
  const coordinator = createApiRestartRecoveryRunCoordinator()
  const oldRun = coordinator.begin()
  const newRun = coordinator.begin()

  assert.notEqual(oldRun.token, newRun.token)
  assert.equal(oldRun.controller.signal.aborted, true)
  assert.equal(coordinator.isCurrent(oldRun), false)
  assert.equal(coordinator.isCurrent(newRun), true)

  coordinator.finish(oldRun)
  assert.equal(coordinator.isCurrent(newRun), true)
  coordinator.cancel(newRun)
  assert.equal(newRun.controller.signal.aborted, true)
  assert.equal(coordinator.isCurrent(newRun), false)
})

test('cancellation stops polling before another probe or refresh', async () => {
  const controller = new AbortController()
  let probes = 0
  let refreshes = 0
  const outcome = await orchestrateApiRestartRecovery({
    baselineInstanceId: 'old-process',
    probe: async () => {
      probes += 1
      controller.abort()
      return { status: 'ok', instance_id: 'new-process' }
    },
    refreshActiveData: async () => {
      refreshes += 1
    },
    signal: controller.signal,
    intervalMs: 0,
    maxAttempts: 3,
    delay: noDelay,
  })

  assert.deepEqual(outcome, { status: 'cancelled', outageObserved: false })
  assert.equal(probes, 1)
  assert.equal(refreshes, 0)
})

test('the restart card owns polling cleanup in a finally block and exposes reset', () => {
  const card = readFileSync(
    path.join(frontendRoot, 'components/system/restart-api-card.tsx'),
    'utf8',
  )

  assert.match(card, /finally \{/)
  assert.match(card, /apiRestartRecoveryRuns\.finish\(run\)/)
  assert.match(card, /if \(pollingRef\.current\?\.token === run\.token\) pollingRef\.current = null/)
  assert.match(card, /onClick=\{resetRecovery\}/)
  assert.match(card, /再次重启/)
})
