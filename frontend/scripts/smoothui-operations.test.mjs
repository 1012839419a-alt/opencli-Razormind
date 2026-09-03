import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildOperationsNodeTasks,
  toOperationsTaskStatus,
} from '../lib/studio/operations-task-model.ts'
import {
  resolveApprovalAvailability,
  shouldIgnoreInboxShortcut,
} from '../lib/inbox/workbench-state.ts'

test('node task projection derives counts and statuses only from node states', () => {
  const tasks = buildOperationsNodeTasks([
    { nodeId: 'fetch-source', status: 'completed', eventCount: 2 },
    { nodeId: 'approval-gate', status: 'blocked', eventCount: 1 },
  ])

  assert.equal(tasks.length, 2)
  assert.equal(tasks.filter((task) => task.status === 'done').length, 1)
  assert.equal(tasks[0]?.note, '2 events · completed')
  assert.equal(tasks[1]?.status, 'blocked')
})

test('node statuses preserve terminal, partial, active, and waiting semantics', () => {
  assert.equal(toOperationsTaskStatus('completed'), 'done')
  assert.equal(toOperationsTaskStatus('failed'), 'failed')
  assert.equal(toOperationsTaskStatus('blocked'), 'blocked')
  assert.equal(toOperationsTaskStatus('partial'), 'partial')
  assert.equal(toOperationsTaskStatus('partial_success'), 'partial')
  assert.equal(toOperationsTaskStatus('running'), 'running')
  assert.equal(toOperationsTaskStatus('queued'), 'pending')
  assert.equal(toOperationsTaskStatus('waiting'), 'pending')
})

test('inbox global shortcuts ignore direct and nested interactive targets', () => {
  for (const tagName of ['input', 'textarea', 'select', 'button', 'a', 'summary']) {
    assert.equal(shouldIgnoreInboxShortcut({ tagName }), true, tagName)
  }
  assert.equal(shouldIgnoreInboxShortcut({ tagName: 'svg', withinInteractive: true }), true)
  assert.equal(shouldIgnoreInboxShortcut({ tagName: 'div', isContentEditable: true }), true)
  assert.equal(shouldIgnoreInboxShortcut({ tagName: 'div' }), false)
})

test('approval availability exposes loading, prerequisite, and error states', () => {
  const ready = {
    workspaceLoading: false,
    workspaceError: false,
    workspaceCount: 1,
    workspaceId: 'workspace-1',
    inboxLoading: false,
    inboxError: false,
  }

  assert.equal(resolveApprovalAvailability({ ...ready, workspaceLoading: true }), 'loading')
  assert.equal(resolveApprovalAvailability({ ...ready, workspaceError: true }), 'workspace_error')
  assert.equal(resolveApprovalAvailability({ ...ready, workspaceCount: 0, workspaceId: null }), 'no_workspace')
  assert.equal(resolveApprovalAvailability({ ...ready, inboxLoading: true }), 'loading')
  assert.equal(resolveApprovalAvailability({ ...ready, inboxError: true }), 'inbox_error')
  assert.equal(resolveApprovalAvailability(ready), 'ready')
})
