export type DeliveryStatusTone = 'informative' | 'positive' | 'warning' | 'negative' | 'neutral'

export interface DeliveryStatusPresentation {
  label: string
  description: string
  tone: DeliveryStatusTone
}

export function sanitizedDeliveryErrorSummary(error?: string | null): string | null {
  if (!error) return null
  const normalized = error.toLowerCase()
  if (/timeout|timed out/.test(normalized)) return '通知通道连接超时'
  if (/certificate|\btls\b|\bssl\b/.test(normalized)) return '通知通道安全校验失败'
  if (/name resolution|dns|resolve host/.test(normalized)) return '无法解析通知通道地址'
  if (/connect|connection/.test(normalized)) return '无法连接通知通道'
  return '通知处理失败（详细错误已隐藏）'
}

export function dedupeDeliveryAttempts<T extends { id: string }>(items: readonly T[]): T[] {
  const seen = new Set<string>()
  return items.filter((item) => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

export function transportStatusPresentation(status: string): DeliveryStatusPresentation {
  switch (status.toLowerCase()) {
    case 'sent':
    case 'success':
    case 'completed':
      return {
        label: '已提交',
        description: '通知请求已被通道接受，不代表业务方已确认。',
        tone: 'informative',
      }
    case 'pending':
    case 'queued':
      return {
        label: '等待提交',
        description: '通知请求仍在等待通道处理。',
        tone: 'warning',
      }
    case 'failed':
    case 'error':
      return {
        label: '提交失败',
        description: '通知请求未成功提交到通道。',
        tone: 'negative',
      }
    default:
      return {
        label: '状态未知',
        description: '后端返回了当前控制台无法识别的提交状态。',
        tone: 'neutral',
      }
  }
}

export function acknowledgementStatusPresentation(
  status: string,
  transportStatus?: string,
): DeliveryStatusPresentation {
  const normalizedStatus = status.toLowerCase()
  const normalizedTransport = transportStatus?.toLowerCase()
  if (
    normalizedStatus === 'not_required' &&
    (normalizedTransport === 'pending' || normalizedTransport === 'queued')
  ) {
    return {
      label: '待提交后确定',
      description: '通知尚未提交，回执要求和状态将在提交后确定。',
      tone: 'neutral',
    }
  }
  if (
    normalizedStatus === 'not_required' &&
    (normalizedTransport === 'failed' || normalizedTransport === 'error')
  ) {
    return {
      label: '未进入回执',
      description: '通知提交失败，因此没有进入业务回执阶段。',
      tone: 'neutral',
    }
  }

  switch (normalizedStatus) {
    case 'acked':
      return {
        label: '已确认',
        description: '业务方已返回有效确认。',
        tone: 'positive',
      }
    case 'pending':
      return {
        label: '等待回执',
        description: '通知已提交，仍在等待业务方确认。',
        tone: 'warning',
      }
    case 'failed':
      return {
        label: '回执失败',
        description: '业务方回执未通过验证或明确失败。',
        tone: 'negative',
      }
    case 'not_required':
      return {
        label: '无需回执',
        description: '该通知通道未配置业务回执。',
        tone: 'neutral',
      }
    default:
      return {
        label: '状态未知',
        description: '后端返回了当前控制台无法识别的回执状态。',
        tone: 'neutral',
      }
  }
}
