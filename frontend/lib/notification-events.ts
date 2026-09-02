export type NotificationTriggerEvent =
  | 'on_new_record'
  | 'on_ai_processed'
  | 'on_task_failed'

export const NOTIFICATION_TRIGGER_EVENTS: readonly {
  value: NotificationTriggerEvent
  label: string
  description: string
}[] = [
  {
    value: 'on_new_record',
    label: '新记录采集',
    description: '采集成功并产生新记录时触发。',
  },
  {
    value: 'on_ai_processed',
    label: 'AI 处理完成',
    description: 'AI 富化完成并产生处理结果时触发。',
  },
  {
    value: 'on_task_failed',
    label: '任务失败',
    description: '采集任务失败时触发，即使本次没有产生记录。',
  },
]

export function notificationTriggerLabel(event: string): string {
  return NOTIFICATION_TRIGGER_EVENTS.find((item) => item.value === event)?.label ?? event
}
