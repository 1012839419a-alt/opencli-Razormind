import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const page = fs.readFileSync(path.join(root, 'app/(app)/notifications/page.tsx'), 'utf8')
const hooks = fs.readFileSync(path.join(root, 'lib/api/hooks.ts'), 'utf8')
const endpoints = fs.readFileSync(path.join(root, 'lib/api/endpoints.ts'), 'utf8')

test('notification center loads paginated delivery evidence', () => {
  assert.match(page, /useInfiniteNotificationLogs\(\{ limit: DELIVERY_PAGE_SIZE \}\)/)
  assert.match(page, /fetchNextPage\(\)/)
  assert.match(page, /已显示 \{logs\.length\} \/ \{totalLogs\} 条/)
})

test('rules and evidence expose independent recovery paths', () => {
  assert.match(page, /rulesQuery\.isError/)
  assert.match(page, /logsQuery\.isError/)
  assert.match(page, /logsQuery\.isError && logs\.length === 0/)
  assert.match(page, /更新投递证据失败，已加载的记录仍保留/)
  assert.match(page, /logsQuery\.refetch\(\)/)
})

test('rule management paginates and missing log rules resolve by exact id', () => {
  assert.match(page, /useInfiniteNotificationRules\(\{ limit: RULE_PAGE_SIZE \}\)/)
  assert.match(page, /useNotificationRulesByIds\(missingRuleIds\)/)
  assert.match(hooks, /api\.getNotificationRule\(id\)/)
  assert.match(endpoints, /`\/notifications\/rules\/\$\{id\}`/)
  assert.doesNotMatch(page, /未知或已删除规则/)
})

test('offset pages are deduplicated and destructive evidence loss is disclosed', () => {
  assert.match(page, /dedupeDeliveryAttempts\(logsQuery\.data/)
  assert.match(page, /永久删除该规则及其全部投递证据，此操作不可恢复/)
})

test('delivery evidence does not render raw transport or ACK payloads', () => {
  assert.doesNotMatch(page, /log\.response_data/)
  assert.doesNotMatch(page, /log\.ack_data/)
  assert.match(page, /sanitizedDeliveryErrorSummary\(log\.error_message\)/)
})

test('deleting a notification rule invalidates its cascaded log view', () => {
  const deletionHook = hooks.slice(
    hooks.indexOf('export function useDeleteNotificationRule'),
    hooks.indexOf('export function useNotificationLogs'),
  )
  assert.match(deletionHook, /queryKey: \['notification-rules'\]/)
  assert.match(deletionHook, /queryKey: \['notification-logs'\]/)
})
