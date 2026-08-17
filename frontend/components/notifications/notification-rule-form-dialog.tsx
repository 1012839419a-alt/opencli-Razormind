'use client'

import { useEffect, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  useCreateNotificationRule,
  useSource,
  useSources,
  useUpdateNotificationRule,
} from '@/lib/api/hooks'
import type { NotificationRule, NotificationRuleInput } from '@/lib/api/types'
import { notificationChannelLabel } from '@/lib/notification-channels'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Field, FieldDescription, FieldGroup, FieldLabel } from '@/components/ui/field'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'

// Notifier types the backend actually registers (backend/notifiers/*, each
// decorated with @register_notifier). Keep in sync with that directory —
// notifier_type is a plain `str` on the schema, so picking anything else
// here would save fine but never fire: notifier_dispatch.py's
// get_notifier() only resolves these five and silently skips unknown rules
// (a warning log, no user-visible error).
const NOTIFIER_TYPES = ['webhook', 'feishu', 'dingtalk', 'wecom', 'email'] as const
type NotifierType = (typeof NOTIFIER_TYPES)[number]

// dispatch_notifications() (backend/pipeline/notifier_dispatch.py) only ever
// fires rules with trigger_event == 'on_new_record' — the backend schema
// (NotificationRuleCreate/Update, backend/schemas/notification.py) rejects
// any other literal with a 422. Fixed value today, not a preview of a wider
// open set — shown disabled rather than as a free choice.
const TRIGGER_EVENT = 'on_new_record'

const ALL_SOURCES = '__all__'

interface FormState {
  name: string
  sourceId: string
  notifierType: NotifierType
  enabled: boolean
  // webhook: notifier_config.url
  url: string
  // feishu / dingtalk / wecom: notifier_config.webhook_url
  webhookUrl: string
  // webhook / feishu / dingtalk: notifier_config.secret
  secret: string
  // feishu / dingtalk: notifier_config.title
  title: string
  // feishu / dingtalk / wecom: notifier_config.content
  content: string
  // webhook / feishu / dingtalk / wecom: notifier_config.timeout
  timeout: string
  // webhook: notifier_config.headers, edited as raw JSON text
  headers: string
  // email
  smtpHost: string
  smtpPort: string
  smtpUser: string
  smtpPassword: string
  emailFrom: string
  emailTo: string
  subject: string
  body: string
  // shared across all notifier types: notifier_config.ack_secret — when
  // set, the dispatcher marks the send ack_status='pending' and expects an
  // HMAC-signed POST /notifications/logs/{id}/ack from the downstream
  // system before it counts as delivered (see _ack_secret in both
  // backend/api/v1/notifications.py and backend/pipeline/notifier_dispatch.py).
  ackSecret: string
  // rule.filter_conditions, edited as raw JSON text
  filterConditions: string
}

const EMPTY_FORM: FormState = {
  name: '',
  sourceId: ALL_SOURCES,
  notifierType: 'webhook',
  enabled: true,
  url: '',
  webhookUrl: '',
  secret: '',
  title: '',
  content: '',
  timeout: '',
  headers: '',
  smtpHost: '',
  smtpPort: '',
  smtpUser: '',
  smtpPassword: '',
  emailFrom: '',
  emailTo: '',
  subject: '',
  body: '',
  ackSecret: '',
  filterConditions: '',
}

function str(value: unknown): string {
  if (typeof value === 'string') return value
  return value != null ? String(value) : ''
}

function isNotifierType(value: string): value is NotifierType {
  return (NOTIFIER_TYPES as readonly string[]).includes(value)
}

// Unlike ModelProvider (has_api_key/api_key_preview mask the raw key —
// see ModelProviderInput's doc comment in lib/api/types.ts), NotificationRule
// does NOT mask notifier_config on read: NotificationRuleRead returns the
// dict as-is. So prefilling secret-shaped fields on edit is not a security
// regression here — the value already reached the client in the list
// response. type="password" below is purely visual masking, not a
// write-only/leave-blank-to-keep-existing contract like the provider form.
function ruleToForm(rule: NotificationRule): FormState {
  const cfg = rule.notifier_config ?? {}
  return {
    name: rule.name,
    sourceId: rule.source_id ?? ALL_SOURCES,
    notifierType: isNotifierType(rule.notifier_type) ? rule.notifier_type : 'webhook',
    enabled: rule.enabled,
    url: str(cfg.url),
    webhookUrl: str(cfg.webhook_url),
    secret: str(cfg.secret),
    title: str(cfg.title),
    content: str(cfg.content),
    timeout: cfg.timeout != null ? String(cfg.timeout) : '',
    headers: cfg.headers ? JSON.stringify(cfg.headers, null, 2) : '',
    smtpHost: str(cfg.smtp_host),
    smtpPort: cfg.smtp_port != null ? String(cfg.smtp_port) : '',
    smtpUser: str(cfg.smtp_user),
    smtpPassword: str(cfg.smtp_password),
    emailFrom: str(cfg.from),
    emailTo: Array.isArray(cfg.to) ? cfg.to.join(', ') : str(cfg.to),
    subject: str(cfg.subject),
    body: str(cfg.body),
    ackSecret: str(cfg.ack_secret),
    filterConditions: rule.filter_conditions ? JSON.stringify(rule.filter_conditions, null, 2) : '',
  }
}

function tryParseJsonObject(
  raw: string,
): { ok: true; value: Record<string, unknown> | undefined } | { ok: false } {
  if (!raw.trim()) return { ok: true, value: undefined }
  try {
    const parsed = JSON.parse(raw)
    if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return { ok: false }
    return { ok: true, value: parsed as Record<string, unknown> }
  } catch {
    return { ok: false }
  }
}

function validate(form: FormState): string | null {
  if (!form.name.trim()) return '请填写规则名称'
  if (form.notifierType === 'webhook' && !form.url.trim()) return '请填写 Webhook URL'
  if (
    (form.notifierType === 'feishu' || form.notifierType === 'dingtalk' || form.notifierType === 'wecom') &&
    !form.webhookUrl.trim()
  )
    return '请填写机器人 Webhook 地址'
  if (form.notifierType === 'email' && !form.emailTo.trim()) return '请填写收件邮箱'
  return null
}

function buildNotifierConfig(
  form: FormState,
  headers: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const config: Record<string, unknown> = {}
  const timeout = form.timeout.trim()

  switch (form.notifierType) {
    case 'webhook':
      config.url = form.url.trim()
      if (form.secret.trim()) config.secret = form.secret.trim()
      if (headers) config.headers = headers
      break
    case 'feishu':
    case 'dingtalk':
      config.webhook_url = form.webhookUrl.trim()
      if (form.secret.trim()) config.secret = form.secret.trim()
      if (form.title.trim()) config.title = form.title.trim()
      if (form.content.trim()) config.content = form.content.trim()
      break
    case 'wecom':
      config.webhook_url = form.webhookUrl.trim()
      if (form.content.trim()) config.content = form.content.trim()
      break
    case 'email': {
      if (form.smtpHost.trim()) config.smtp_host = form.smtpHost.trim()
      if (form.smtpPort.trim()) config.smtp_port = Number(form.smtpPort.trim())
      if (form.smtpUser.trim()) config.smtp_user = form.smtpUser.trim()
      if (form.smtpPassword.trim()) config.smtp_password = form.smtpPassword.trim()
      if (form.emailFrom.trim()) config.from = form.emailFrom.trim()
      const to = form.emailTo
        .split(/[,\s]+/)
        .map((address) => address.trim())
        .filter(Boolean)
      if (to.length) config.to = to
      if (form.subject.trim()) config.subject = form.subject.trim()
      if (form.body.trim()) config.body = form.body.trim()
      break
    }
  }

  if (form.notifierType !== 'email' && timeout) config.timeout = Number(timeout)
  if (form.ackSecret.trim()) config.ack_secret = form.ackSecret.trim()
  return config
}

export function NotificationRuleFormDialog({
  mode,
  rule,
  triggerLabel,
  triggerIcon,
  triggerVariant = 'default',
  triggerSize = 'sm',
  triggerAriaLabel,
}: {
  mode: 'create' | 'edit'
  rule?: NotificationRule
  triggerLabel: string
  triggerIcon?: React.ReactNode
  triggerVariant?: React.ComponentProps<typeof Button>['variant']
  triggerSize?: React.ComponentProps<typeof Button>['size']
  /** Required when triggerLabel is empty (icon-only trigger) so the button stays accessible. */
  triggerAriaLabel?: string
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(() => (rule ? ruleToForm(rule) : EMPTY_FORM))
  const createMutation = useCreateNotificationRule()
  const updateMutation = useUpdateNotificationRule()
  // Only resolves once the edit dialog for a source-scoped rule is actually
  // open — avoids firing a lookup for every row's (closed) dialog instance.
  const editSourceQuery = useSource(
    mode === 'edit' && open && rule?.source_id ? rule.source_id : null,
  )
  const pending = createMutation.isPending || updateMutation.isPending

  useEffect(() => {
    if (!open) return
    setForm(rule ? ruleToForm(rule) : EMPTY_FORM)
  }, [open, rule])

  const finish = (message: string) => {
    toast.success(message)
    setOpen(false)
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    const validationError = validate(form)
    if (validationError) {
      toast.error(validationError)
      return
    }

    const headersResult =
      form.notifierType === 'webhook'
        ? tryParseJsonObject(form.headers)
        : ({ ok: true, value: undefined } as const)
    if (!headersResult.ok) {
      toast.error('自定义请求头必须是合法的 JSON 对象')
      return
    }

    const filterResult = tryParseJsonObject(form.filterConditions)
    if (!filterResult.ok) {
      toast.error('触发条件必须是合法的 JSON 对象')
      return
    }

    const payload: NotificationRuleInput = {
      name: form.name.trim(),
      trigger_event: TRIGGER_EVENT,
      notifier_type: form.notifierType,
      notifier_config: buildNotifierConfig(form, headersResult.value),
      filter_conditions: filterResult.value ?? null,
      enabled: form.enabled,
    }
    // source_id is only settable at creation — NotificationRuleUpdate has no
    // source_id field on the backend (see NotificationRuleInput's doc
    // comment), so sending it on PATCH would silently no-op. Keep edit
    // payloads honest about what they can actually change.
    if (mode === 'create') {
      payload.source_id = form.sourceId === ALL_SOURCES ? null : form.sourceId
    }

    const onError = (error: Error) => toast.error(error.message)

    if (mode === 'create') {
      createMutation.mutate(payload, { onSuccess: () => finish('通知规则已创建'), onError })
      return
    }
    if (rule) {
      updateMutation.mutate(
        { id: rule.id, data: payload },
        { onSuccess: () => finish('通知规则已更新'), onError },
      )
    }
  }

  const showSecret =
    form.notifierType === 'webhook' || form.notifierType === 'feishu' || form.notifierType === 'dingtalk'
  const showTitle = form.notifierType === 'feishu' || form.notifierType === 'dingtalk'
  const showContent =
    form.notifierType === 'feishu' || form.notifierType === 'dingtalk' || form.notifierType === 'wecom'
  const showTimeout = form.notifierType !== 'email'
  const showHeaders = form.notifierType === 'webhook'

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={<Button variant={triggerVariant} size={triggerSize} aria-label={triggerAriaLabel} />}
      >
        {triggerIcon}
        {triggerLabel}
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{mode === 'create' ? '创建通知规则' : '编辑通知规则'}</DialogTitle>
            <DialogDescription>
              {mode === 'create'
                ? '选择触发来源和投递方式，采集到新记录时自动通知。'
                : '更新投递方式或触发条件；来源筛选创建后无法更改。'}
            </DialogDescription>
          </DialogHeader>

          <FieldGroup className="gap-5">
            <Field>
              <FieldLabel htmlFor="rule-name">规则名称</FieldLabel>
              <Input
                id="rule-name"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="例如：新纪录 Slack 通知"
                required
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="rule-notifier-type">通知方式</FieldLabel>
                <Select
                  value={form.notifierType}
                  onValueChange={(value) =>
                    setForm((current) => ({ ...current, notifierType: value as NotifierType }))
                  }
                >
                  <SelectTrigger id="rule-notifier-type" className="w-full">
                    <SelectValue>{notificationChannelLabel(form.notifierType)}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {NOTIFIER_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {notificationChannelLabel(type)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              {mode === 'create' ? (
                <Field>
                  <FieldLabel htmlFor="rule-source">触发来源</FieldLabel>
                  <SourcePicker
                    value={form.sourceId}
                    onChange={(value) => setForm((current) => ({ ...current, sourceId: value }))}
                  />
                </Field>
              ) : (
                <Field>
                  <FieldLabel htmlFor="rule-source-readonly">触发来源</FieldLabel>
                  <Input
                    id="rule-source-readonly"
                    value={rule?.source_id ? (editSourceQuery.data?.name ?? rule.source_id) : '全部来源'}
                    disabled
                  />
                  <FieldDescription>来源筛选只能在创建时设置，无法在编辑中更改。</FieldDescription>
                </Field>
              )}
            </div>

            {form.notifierType === 'webhook' ? (
              <Field>
                <FieldLabel htmlFor="rule-url">Webhook URL</FieldLabel>
                <Input
                  id="rule-url"
                  value={form.url}
                  onChange={(event) => setForm((current) => ({ ...current, url: event.target.value }))}
                  placeholder="https://example.com/hooks/notify"
                  inputMode="url"
                />
              </Field>
            ) : null}

            {form.notifierType === 'feishu' || form.notifierType === 'dingtalk' || form.notifierType === 'wecom' ? (
              <Field>
                <FieldLabel htmlFor="rule-webhook-url">机器人 Webhook 地址</FieldLabel>
                <Input
                  id="rule-webhook-url"
                  value={form.webhookUrl}
                  onChange={(event) => setForm((current) => ({ ...current, webhookUrl: event.target.value }))}
                  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/…"
                  inputMode="url"
                />
              </Field>
            ) : null}

            {form.notifierType === 'email' ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field className="sm:col-span-2">
                  <FieldLabel htmlFor="rule-email-to">收件邮箱</FieldLabel>
                  <Input
                    id="rule-email-to"
                    value={form.emailTo}
                    onChange={(event) => setForm((current) => ({ ...current, emailTo: event.target.value }))}
                    placeholder="a@example.com, b@example.com"
                  />
                  <FieldDescription>多个地址用逗号分隔。</FieldDescription>
                </Field>
                <Field>
                  <FieldLabel htmlFor="rule-smtp-host">SMTP 服务器</FieldLabel>
                  <Input
                    id="rule-smtp-host"
                    value={form.smtpHost}
                    onChange={(event) => setForm((current) => ({ ...current, smtpHost: event.target.value }))}
                    placeholder="留空则使用服务端环境变量"
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="rule-smtp-user">SMTP 用户名</FieldLabel>
                  <Input
                    id="rule-smtp-user"
                    value={form.smtpUser}
                    onChange={(event) => setForm((current) => ({ ...current, smtpUser: event.target.value }))}
                  />
                </Field>
                <Field className="sm:col-span-2">
                  <FieldLabel htmlFor="rule-smtp-password">SMTP 密码</FieldLabel>
                  <Input
                    id="rule-smtp-password"
                    type="password"
                    value={form.smtpPassword}
                    onChange={(event) => setForm((current) => ({ ...current, smtpPassword: event.target.value }))}
                    autoComplete="new-password"
                  />
                </Field>
              </div>
            ) : null}

            <Field>
              <FieldLabel htmlFor="rule-trigger-event">触发事件</FieldLabel>
              <Input id="rule-trigger-event" value={TRIGGER_EVENT} disabled />
              <FieldDescription>
                当前仅支持&ldquo;新纪录采集&rdquo;这一种触发事件；调度链路还没有其他事件的生产者，选择其他值会被后端拒绝。
              </FieldDescription>
            </Field>

            <Field orientation="horizontal" className="items-center justify-between">
              <FieldLabel htmlFor="rule-enabled">启用规则</FieldLabel>
              <Switch
                id="rule-enabled"
                checked={form.enabled}
                onCheckedChange={(value) => setForm((current) => ({ ...current, enabled: value }))}
              />
            </Field>
          </FieldGroup>

          <details className="group rounded-lg border bg-muted/15">
            <summary className="flex cursor-pointer list-none items-center justify-between px-4 py-3 text-sm font-medium">
              高级设置
              <ChevronDown className="size-4 text-muted-foreground transition-transform group-open:rotate-180" />
            </summary>
            <div className="grid gap-4 border-t p-4">
              {showSecret ? (
                <Field>
                  <FieldLabel htmlFor="rule-secret">签名密钥</FieldLabel>
                  <Input
                    id="rule-secret"
                    type="password"
                    value={form.secret}
                    onChange={(event) => setForm((current) => ({ ...current, secret: event.target.value }))}
                    autoComplete="new-password"
                    placeholder="留空则不校验签名"
                  />
                </Field>
              ) : null}

              {showTitle ? (
                <Field>
                  <FieldLabel htmlFor="rule-title">标题模板</FieldLabel>
                  <Input
                    id="rule-title"
                    value={form.title}
                    onChange={(event) => setForm((current) => ({ ...current, title: event.target.value }))}
                    placeholder="支持 {{title}} 等占位符"
                  />
                </Field>
              ) : null}

              {showContent ? (
                <Field>
                  <FieldLabel htmlFor="rule-content">内容模板</FieldLabel>
                  <Textarea
                    id="rule-content"
                    value={form.content}
                    onChange={(event) => setForm((current) => ({ ...current, content: event.target.value }))}
                    placeholder="支持 {{title}}、{{source_id}} 等占位符"
                    rows={3}
                  />
                </Field>
              ) : null}

              {form.notifierType === 'email' ? (
                <>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field>
                      <FieldLabel htmlFor="rule-smtp-port">SMTP 端口</FieldLabel>
                      <Input
                        id="rule-smtp-port"
                        type="number"
                        value={form.smtpPort}
                        onChange={(event) => setForm((current) => ({ ...current, smtpPort: event.target.value }))}
                        placeholder="587"
                      />
                    </Field>
                    <Field>
                      <FieldLabel htmlFor="rule-email-from">发件地址</FieldLabel>
                      <Input
                        id="rule-email-from"
                        value={form.emailFrom}
                        onChange={(event) => setForm((current) => ({ ...current, emailFrom: event.target.value }))}
                        placeholder="留空则使用 SMTP 用户名"
                      />
                    </Field>
                  </div>
                  <Field>
                    <FieldLabel htmlFor="rule-subject">主题模板</FieldLabel>
                    <Input
                      id="rule-subject"
                      value={form.subject}
                      onChange={(event) => setForm((current) => ({ ...current, subject: event.target.value }))}
                      placeholder="支持 {{title}} 等占位符"
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor="rule-body">正文模板</FieldLabel>
                    <Textarea
                      id="rule-body"
                      value={form.body}
                      onChange={(event) => setForm((current) => ({ ...current, body: event.target.value }))}
                      rows={3}
                    />
                  </Field>
                </>
              ) : null}

              {showTimeout ? (
                <Field>
                  <FieldLabel htmlFor="rule-timeout">超时时间（秒）</FieldLabel>
                  <Input
                    id="rule-timeout"
                    type="number"
                    value={form.timeout}
                    onChange={(event) => setForm((current) => ({ ...current, timeout: event.target.value }))}
                    placeholder="15"
                  />
                </Field>
              ) : null}

              {showHeaders ? (
                <Field>
                  <FieldLabel htmlFor="rule-headers">自定义请求头（JSON）</FieldLabel>
                  <Textarea
                    id="rule-headers"
                    value={form.headers}
                    onChange={(event) => setForm((current) => ({ ...current, headers: event.target.value }))}
                    placeholder='{"X-Custom": "value"}'
                    rows={2}
                    className="font-mono text-xs"
                  />
                </Field>
              ) : null}

              <Field>
                <FieldLabel htmlFor="rule-ack-secret">回执密钥（可选）</FieldLabel>
                <Input
                  id="rule-ack-secret"
                  type="password"
                  value={form.ackSecret}
                  onChange={(event) => setForm((current) => ({ ...current, ackSecret: event.target.value }))}
                  autoComplete="new-password"
                />
                <FieldDescription>
                  设置后，投递记录会等待下游用 HMAC 签名的请求确认收到，否则会保持&ldquo;待确认&rdquo;状态。
                </FieldDescription>
              </Field>

              <Field>
                <FieldLabel htmlFor="rule-filter-conditions">触发条件（JSON，可选）</FieldLabel>
                <Textarea
                  id="rule-filter-conditions"
                  value={form.filterConditions}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, filterConditions: event.target.value }))
                  }
                  placeholder='{"field": "value"}'
                  rows={3}
                  className="font-mono text-xs"
                />
                <FieldDescription>留空表示该来源下的所有新记录都会触发通知。</FieldDescription>
              </Field>
            </div>
          </details>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              {pending ? '保存中…' : mode === 'create' ? '创建规则' : '保存更改'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function SourcePicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const { data, isLoading } = useSources({ limit: 100 })
  const sources = data?.data ?? []
  const selectedLabel =
    value === ALL_SOURCES
      ? '全部来源'
      : (sources.find((source) => source.id === value)?.name ?? (isLoading ? '加载中…' : '选择来源'))

  return (
    <Select value={value} onValueChange={(next) => onChange(next as string)}>
      <SelectTrigger id="rule-source" className="w-full">
        <SelectValue>{selectedLabel}</SelectValue>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={ALL_SOURCES}>全部来源</SelectItem>
        {sources.map((source) => (
          <SelectItem key={source.id} value={source.id}>
            {source.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
