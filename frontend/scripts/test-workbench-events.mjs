import assert from 'node:assert/strict'

import {
  consumeWorkbenchSse,
  mergeWorkbenchEvents,
} from '../lib/workbench/events.ts'

const event = (sequence, eventType = 'text') => ({
  id: `event-${sequence}`,
  sequence,
  eventType,
  payload: { text: `event ${sequence}` },
  createdAt: '2026-08-29T00:00:00Z',
})

let passed = 0

function test(name, run) {
  run()
  passed += 1
  console.log(`ok - ${name}`)
}

test('replay and reconnect events are sequence-deduplicated and ordered', () => {
  const replay = [event(1), event(3)]
  const afterReconnect = mergeWorkbenchEvents(replay, event(2))
  const duplicate = mergeWorkbenchEvents(afterReconnect, event(3, 'state'))

  assert.deepEqual(afterReconnect.map((item) => item.sequence), [1, 2, 3])
  assert.deepEqual(duplicate.map((item) => item.sequence), [1, 2, 3])
  assert.equal(duplicate[2].eventType, 'state')
})

test('split SSE frames preserve an incomplete suffix and route terminal state', () => {
  const received = []
  const states = []
  const callbacks = {
    onEvent: (item) => received.push(item),
    onState: (state) => states.push(state),
  }
  const serialized = JSON.stringify(event(4, 'tool_result'))
  const first = consumeWorkbenchSse(`id: 4\nevent: workbench_event\ndata: ${serialized.slice(0, 18)}`, callbacks)
  const rest = consumeWorkbenchSse(`${first}${serialized.slice(18)}\n\nevent: turn_state\ndata: {"turnId":"turn-1","status":"proposed"}\n\n`, callbacks)

  assert.equal(rest, '')
  assert.equal(received.length, 1)
  assert.equal(received[0].sequence, 4)
  assert.deepEqual(states, [{ turnId: 'turn-1', status: 'proposed' }])
})

console.log(`\n${passed} passed`)
