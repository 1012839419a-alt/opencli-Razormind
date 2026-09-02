import assert from 'node:assert/strict'
import { test } from 'node:test'

import { groupFailures, groupStreamTasks } from '../lib/monitor/task-grouping.ts'

const streamTask = {
  id: 'run-1',
  href: '/tasks/task-1',
  lane: 'collect',
  title: '同名采集',
  endpoint: 'source',
  workerId: 'worker-1',
  workerName: 'worker',
  phase: 'failed',
  records: 1,
  retries: 0,
  startedAt: 1,
  durationMs: 10,
}

test('stream grouping never merges different authoritative task destinations', () => {
  const grouped = groupStreamTasks([
    streamTask,
    { ...streamTask, id: 'run-2', href: '/tasks/task-2', records: 2 },
  ])

  assert.equal(grouped.length, 2)
  assert.deepEqual(grouped.map((task) => task.href), ['/tasks/task-1', '/tasks/task-2'])
})

test('stream grouping still combines repeated runs of the same task', () => {
  const grouped = groupStreamTasks([
    streamTask,
    { ...streamTask, id: 'run-2', records: 2 },
  ])

  assert.equal(grouped.length, 1)
  assert.equal(grouped[0].occurrences, 2)
  assert.equal(grouped[0].records, 3)
  assert.equal(grouped[0].href, '/tasks/task-1')
})

test('failure grouping preserves distinct task destinations', () => {
  const failure = {
    id: 'failure-1',
    href: '/tasks/task-1',
    lane: 'collect',
    title: '同名采集',
    workerName: 'worker',
    error: 'timeout',
    retries: 0,
    at: 1,
  }
  const grouped = groupFailures([
    failure,
    { ...failure, id: 'failure-2', href: '/tasks/task-2' },
  ])

  assert.equal(grouped.length, 2)
  assert.deepEqual(grouped.map((item) => item.href), ['/tasks/task-1', '/tasks/task-2'])
})
