export function automationScheduleText(value: string) {
  const [kind, time] = value.split('@')
  const label = kind === 'daily' ? '每天' : kind === 'weekdays' ? '工作日' : kind === 'weekly' ? '每周' : kind === 'hourly' ? '每小时' : kind
  return `${label}${time ? ` ${time}` : ''}`
}

export function automationScheduleValue(kind: string, time: string) {
  return kind === 'hourly' ? 'hourly' : `${kind}@${time}`
}
