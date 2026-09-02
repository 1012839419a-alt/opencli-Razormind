import type { FailureItem, StreamTask } from '@/lib/demo/monitor'

export type GroupedStreamTask = StreamTask & { occurrences: number }
export type GroupedFailure = FailureItem & { occurrences: number }

export function groupStreamTasks(tasks: StreamTask[]): GroupedStreamTask[] {
  const grouped = new Map<string, GroupedStreamTask>()

  for (const task of tasks) {
    const key = [task.href ?? '', task.title, task.lane, task.workerName, task.phase].join('\u0000')
    const existing = grouped.get(key)
    if (existing) {
      existing.occurrences += 1
      existing.records += task.records
      continue
    }
    grouped.set(key, { ...task, occurrences: 1 })
  }

  return Array.from(grouped.values()).slice(0, 6)
}

export function groupFailures(failures: FailureItem[]): GroupedFailure[] {
  const grouped = new Map<string, GroupedFailure>()

  for (const failure of failures) {
    const key = [failure.href ?? '', failure.title, failure.workerName, failure.error].join('\u0000')
    const existing = grouped.get(key)
    if (existing) {
      existing.occurrences += 1
      continue
    }
    grouped.set(key, { ...failure, occurrences: 1 })
  }

  return Array.from(grouped.values()).slice(0, 5)
}
