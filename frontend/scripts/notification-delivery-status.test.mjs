import assert from 'node:assert/strict'
import test from 'node:test'

import {
  acknowledgementStatusPresentation,
  dedupeDeliveryAttempts,
  sanitizedDeliveryErrorSummary,
  transportStatusPresentation,
} from '../lib/notifications/delivery-status.ts'

test('a successful transport is submitted, never presented as confirmed delivery', () => {
  const status = transportStatusPresentation('sent')

  assert.equal(status.label, '已提交')
  assert.doesNotMatch(status.label, /送达|确认/)
  assert.match(status.description, /不代表业务方已确认/)
})

test('transport failures remain operationally distinct from ACK failures', () => {
  assert.deepEqual(transportStatusPresentation('failed'), {
    label: '提交失败',
    description: '通知请求未成功提交到通道。',
    tone: 'negative',
  })
  assert.deepEqual(acknowledgementStatusPresentation('failed'), {
    label: '回执失败',
    description: '业务方回执未通过验证或明确失败。',
    tone: 'negative',
  })
})

test('all backend ACK states have explicit product semantics', () => {
  assert.equal(acknowledgementStatusPresentation('acked', 'sent').label, '已确认')
  assert.equal(acknowledgementStatusPresentation('pending', 'sent').label, '等待回执')
  assert.equal(acknowledgementStatusPresentation('not_required', 'sent').label, '无需回执')
})

test('provisional ACK defaults are not mistaken for final no-ACK semantics', () => {
  assert.equal(
    acknowledgementStatusPresentation('not_required', 'pending').label,
    '待提交后确定',
  )
  assert.equal(
    acknowledgementStatusPresentation('not_required', 'failed').label,
    '未进入回执',
  )
})

test('a real downstream ACK outranks a transport-side failure inference', () => {
  assert.equal(acknowledgementStatusPresentation('acked', 'failed').label, '已确认')
  assert.equal(acknowledgementStatusPresentation('failed', 'failed').label, '回执失败')
  assert.equal(acknowledgementStatusPresentation('pending', 'failed').label, '等待回执')
})

test('unknown backend values fail closed to an unknown state', () => {
  assert.equal(transportStatusPresentation('unexpected').label, '状态未知')
  assert.equal(acknowledgementStatusPresentation('unexpected').label, '状态未知')
})

test('error summaries use an allow-list and never repeat secret-shaped input', () => {
  assert.equal(
    sanitizedDeliveryErrorSummary(
      'Authorization: Bearer sk-live-secret; password=hunter2; Cookie=session-secret',
    ),
    '通知处理失败（详细错误已隐藏）',
  )
  assert.equal(sanitizedDeliveryErrorSummary('ConnectTimeout: POST https://secret.example'), '通知通道连接超时')
  assert.equal(sanitizedDeliveryErrorSummary(null), null)
})

test('offset pagination duplicates are removed by stable delivery id', () => {
  assert.deepEqual(
    dedupeDeliveryAttempts([
      { id: 'new', page: 1 },
      { id: 'boundary', page: 1 },
      { id: 'boundary', page: 2 },
      { id: 'old', page: 2 },
    ]),
    [
      { id: 'new', page: 1 },
      { id: 'boundary', page: 1 },
      { id: 'old', page: 2 },
    ],
  )
})
