import { cpSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const standaloneRoot = path.join(frontendRoot, '.next', 'standalone')

cpSync(path.join(frontendRoot, 'public'), path.join(standaloneRoot, 'public'), {
  force: true,
  recursive: true,
})
cpSync(path.join(frontendRoot, '.next', 'static'), path.join(standaloneRoot, '.next', 'static'), {
  force: true,
  recursive: true,
})

process.env.NODE_ENV = 'production'
await import(pathToFileURL(path.join(standaloneRoot, 'server.js')).href)
