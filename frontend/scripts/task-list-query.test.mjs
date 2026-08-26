import assert from 'node:assert/strict'
import { test } from 'node:test'

import {
  normalizeTaskPage,
  normalizeTaskStatus,
  pathWithQuery,
  queryForTaskPage,
  queryForTaskStatus,
} from '../lib/tasks/query.ts'

test('task filters accept only supported status and positive integer pages', () => {
  assert.equal(normalizeTaskStatus('failed'), 'failed')
  assert.equal(normalizeTaskStatus('unknown'), '')
  assert.equal(normalizeTaskStatus(null), '')
  assert.equal(normalizeTaskPage('3'), 3)
  assert.equal(normalizeTaskPage('0'), 1)
  assert.equal(normalizeTaskPage('2.5'), 1)
  assert.equal(normalizeTaskPage('not-a-number'), 1)
})

test('changing status resets pagination while preserving unrelated context', () => {
  assert.equal(queryForTaskStatus('page=4&source=alpha', 'failed'), 'source=alpha&status=failed')
  assert.equal(queryForTaskStatus('status=failed&page=2&source=alpha', ''), 'source=alpha')
  assert.equal(queryForTaskStatus('page=2', 'unknown'), '')
})

test('changing pages keeps filters and canonicalizes the first page', () => {
  assert.equal(queryForTaskPage('status=failed&source=alpha', 3), 'status=failed&source=alpha&page=3')
  assert.equal(queryForTaskPage('status=failed&page=3', 1), 'status=failed')
  assert.equal(queryForTaskPage('status=failed&page=3', -1), 'status=failed')
  assert.equal(pathWithQuery('/tasks', 'status=failed&page=3'), '/tasks?status=failed&page=3')
  assert.equal(pathWithQuery('/tasks', ''), '/tasks')
})
