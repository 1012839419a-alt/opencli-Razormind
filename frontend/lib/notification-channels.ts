const NOTIFICATION_CHANNEL_LABELS: Record<string, string> = {
  webhook: 'Webhook',
  email: '邮件',
  slack: 'Slack',
  feishu: '飞书',
  dingtalk: '钉钉',
  wecom: '企业微信',
  wechat: '微信',
  qq: 'QQ',
}

export function notificationChannelLabel(channel: string): string {
  return NOTIFICATION_CHANNEL_LABELS[channel.toLowerCase()] ?? channel
}
