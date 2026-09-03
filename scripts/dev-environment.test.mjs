import assert from 'node:assert/strict'
import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import test from 'node:test'

const root = process.cwd()
const script = path.join(root, 'scripts', 'dev-environment.mjs')
const validCore = `API_AUTH_TOKEN=a\nBOOTSTRAP_ADMIN_TOKEN=b\nSECRET_KEY=c\nCREDENTIAL_ENCRYPTION_KEY=d\nDATABASE_URL=sqlite+aiosqlite:///test.db\nCHROME_SUFFIX=\n`

function envFile(contents) {
  const directory = mkdtempSync(path.join(tmpdir(), 'opencli-env-doctor-'))
  const file = path.join(directory, '.env')
  writeFileSync(file, contents)
  return file
}

function doctorArgs(file, ...extraArgs) {
  return [script, `--env-file=${file}`, '--skip-tools', ...extraArgs]
}

test('accepts the default core profile with an empty Chrome suffix', () => {
  const output = execFileSync(process.execPath, doctorArgs(envFile(validCore)), {
    cwd: root,
    encoding: 'utf8',
  })
  assert.match(output, /Environment ready: core/)
})

test('rejects embedded Chrome without the image suffix', () => {
  const result = spawnSync(
    process.execPath,
    doctorArgs(envFile(validCore), '--profiles=embedded-chrome'),
    {
      cwd: root,
      encoding: 'utf8',
    },
  )
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /CHROME_SUFFIX (?:is required|must be -chrome)/)
})

test('accepts AGENT_REGISTER=off without a central URL', () => {
  const file = envFile(`${validCore}AGENT_REGISTER=off\n`)
  const output = execFileSync(process.execPath, doctorArgs(file, '--profiles=agent'), {
    cwd: root,
    encoding: 'utf8',
  })
  assert.match(output, /Environment ready: core, agent/)
})

test('allows active registration modes to skip auto-registration without a central URL', () => {
  for (const registration of ['http', 'ws']) {
    const file = envFile(`${validCore}AGENT_REGISTER=${registration}\n`)
    const output = execFileSync(process.execPath, doctorArgs(file, '--profiles=agent'), {
      cwd: root,
      encoding: 'utf8',
    })
    assert.match(output, /CENTRAL_API_URL is empty; auto-registration is disabled/)
  }
})

test('accepts HTTP registration with an auto-detected advertised URL', () => {
  const file = envFile(`${validCore}CENTRAL_API_URL=http://center:8031\nAGENT_REGISTER=http\n`)
  const output = execFileSync(process.execPath, doctorArgs(file, '--profiles=agent'), {
    cwd: root,
    encoding: 'utf8',
  })
  assert.match(output, /AGENT_ADVERTISE_URL is empty; the agent URL will be auto-detected/)
})

test('accepts WS registration with an auto-detected advertised URL', () => {
  const file = envFile(`${validCore}CENTRAL_API_URL=http://center:8031\nAGENT_REGISTER=ws\n`)
  const output = execFileSync(process.execPath, doctorArgs(file, '--profiles=agent'), {
    cwd: root,
    encoding: 'utf8',
  })
  assert.match(output, /Environment ready: core, agent/)
})

test('rejects an unsupported agent registration mode', () => {
  const file = envFile(`${validCore}AGENT_REGISTER=udp\n`)
  const result = spawnSync(process.execPath, doctorArgs(file, '--profiles=agent'), {
    cwd: root,
    encoding: 'utf8',
  })
  assert.notEqual(result.status, 0)
  assert.match(result.stderr, /AGENT_REGISTER must be http, ws, or off/)
})
