'use client'

import { useEffect, useState } from 'react'
import { ChevronDown, Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { useCreateAgent, useProviders, useUpdateAgent } from '@/lib/api/hooks'
import type { AIAgent } from '@/lib/api/types'
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

// Keep in sync with backend/models/agent.py's "claude | openai | local" comment
// and AIAgentCreate.processor_type — the schema stores a plain str, so this is
// a UX constraint, not an enum enforced server-side.
const PROCESSOR_TYPES = ['claude', 'openai', 'local'] as const
type ProcessorType = (typeof PROCESSOR_TYPES)[number]

// Mirrors the label map in app/(app)/agents/page.tsx (kept local/duplicated
// there too — this codebase does not share these tiny label maps across files).
const PROCESSOR_LABEL: Record<ProcessorType, string> = {
  claude: 'Claude',
  openai: 'OpenAI',
  local: '本地模型',
}

// Sentinel for "no linked provider" — Select items need a non-empty value.
const NO_PROVIDER = '__none__'

interface FormState {
  name: string
  description: string
  processor_type: ProcessorType
  model: string
  provider_id: string
  prompt_template: string
  // processor_config edited as raw JSON text, parsed on submit (same approach
  // as filter_conditions/headers in notification-rule-form-dialog.tsx).
  processor_config: string
  enabled: boolean
}

const EMPTY_FORM: FormState = {
  name: '',
  description: '',
  processor_type: 'claude',
  model: '',
  provider_id: NO_PROVIDER,
  prompt_template: '',
  processor_config: '',
  enabled: true,
}

function isProcessorType(value: string): value is ProcessorType {
  return (PROCESSOR_TYPES as readonly string[]).includes(value)
}

function agentToForm(agent: AIAgent): FormState {
  return {
    name: agent.name,
    description: agent.description ?? '',
    processor_type: isProcessorType(agent.processor_type) ? agent.processor_type : 'claude',
    model: agent.model ?? '',
    provider_id: agent.provider_id ?? NO_PROVIDER,
    prompt_template: agent.prompt_template ?? '',
    processor_config:
      agent.processor_config && Object.keys(agent.processor_config).length > 0
        ? JSON.stringify(agent.processor_config, null, 2)
        : '',
    enabled: agent.enabled,
  }
}

export function AgentFormDialog({
  mode,
  agent,
  triggerLabel,
  triggerIcon,
  triggerVariant = 'default',
  triggerSize = 'sm',
}: {
  mode: 'create' | 'edit'
  agent?: AIAgent
  triggerLabel: string
  triggerIcon?: React.ReactNode
  triggerVariant?: React.ComponentProps<typeof Button>['variant']
  triggerSize?: React.ComponentProps<typeof Button>['size']
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(() => (agent ? agentToForm(agent) : EMPTY_FORM))
  const providersQuery = useProviders()
  const providers = providersQuery.data?.data ?? []
  const createMutation = useCreateAgent()
  const updateMutation = useUpdateAgent()
  const pending = createMutation.isPending || updateMutation.isPending

  useEffect(() => {
    if (!open) return
    setForm(agent ? agentToForm(agent) : EMPTY_FORM)
  }, [open, agent])

  const finish = (message: string) => {
    toast.success(message)
    setOpen(false)
  }

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!form.name.trim()) {
      toast.error('请填写 Agent 名称')
      return
    }

    let processorConfig: Record<string, unknown> | undefined
    if (form.processor_config.trim()) {
      try {
        const parsed = JSON.parse(form.processor_config)
        if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
          throw new Error('not an object')
        }
        processorConfig = parsed as Record<string, unknown>
      } catch {
        toast.error('处理器配置必须是合法的 JSON 对象')
        return
      }
    }

    const payload: Partial<AIAgent> = {
      processor_type: form.processor_type,
      prompt_template: form.prompt_template,
      enabled: form.enabled,
    }
    payload.name = form.name.trim()
    if (form.description.trim()) payload.description = form.description.trim()
    if (form.model.trim()) payload.model = form.model.trim()
    if (form.provider_id !== NO_PROVIDER) payload.provider_id = form.provider_id
    if (processorConfig) payload.processor_config = processorConfig

    const onError = (error: Error) => toast.error(error.message)

    if (mode === 'create') {
      createMutation.mutate(payload, { onSuccess: () => finish('Agent 已创建'), onError })
      return
    }
    if (agent) {
      updateMutation.mutate(
        { id: agent.id, data: payload },
        { onSuccess: () => finish('Agent 已更新'), onError },
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant={triggerVariant} size={triggerSize} />}>
        {triggerIcon}
        {triggerLabel}
      </DialogTrigger>
      <DialogContent className="max-h-[88vh] overflow-y-auto sm:max-w-2xl">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{mode === 'create' ? '创建 Agent' : '编辑 Agent'}</DialogTitle>
            <DialogDescription>
              {mode === 'create'
                ? '配置处理器类型、模型和提示词模板，用于分析和富化采集到的数据。'
                : '更新处理器配置、提示词模板或启用状态。'}
            </DialogDescription>
          </DialogHeader>

          <FieldGroup className="gap-5">
            <Field>
              <FieldLabel htmlFor="agent-name">名称</FieldLabel>
              <Input
                id="agent-name"
                value={form.name}
                onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))}
                placeholder="例如：舆情摘要 Agent"
                required
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field>
                <FieldLabel htmlFor="agent-processor-type">处理器类型</FieldLabel>
                <Select
                  value={form.processor_type}
                  onValueChange={(value) =>
                    setForm((current) => ({ ...current, processor_type: value as ProcessorType }))
                  }
                >
                  <SelectTrigger id="agent-processor-type" className="w-full">
                    {/* Base UI's SelectValue shows the raw value string unless told how
                        to format it — see the note on the schedule-agent Select in
                        schedule-form-dialog.tsx. */}
                    <SelectValue>
                      {(value: ProcessorType | null) => (value ? PROCESSOR_LABEL[value] : '')}
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {PROCESSOR_TYPES.map((type) => (
                      <SelectItem key={type} value={type}>
                        {PROCESSOR_LABEL[type]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>

              <Field>
                <FieldLabel htmlFor="agent-provider">关联供应商</FieldLabel>
                <Select
                  value={form.provider_id}
                  onValueChange={(value) =>
                    setForm((current) => ({ ...current, provider_id: value as string }))
                  }
                >
                  <SelectTrigger id="agent-provider" className="w-full">
                    <SelectValue>
                      {(value: string | null) =>
                        !value || value === NO_PROVIDER
                          ? '不关联供应商'
                          : (providers.find((provider) => provider.id === value)?.name ??
                              (providersQuery.isLoading ? '加载中…' : value))
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NO_PROVIDER}>不关联供应商</SelectItem>
                    {providers.map((provider) => (
                      <SelectItem key={provider.id} value={provider.id}>
                        {provider.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldDescription>用于提供该 Agent 调用模型所需的连接与凭证。</FieldDescription>
              </Field>
            </div>

            <Field>
              <FieldLabel htmlFor="agent-model">模型</FieldLabel>
              <Input
                id="agent-model"
                value={form.model}
                onChange={(event) => setForm((current) => ({ ...current, model: event.target.value }))}
                placeholder="留空则使用供应商默认模型"
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="agent-description">描述</FieldLabel>
              <Textarea
                id="agent-description"
                value={form.description}
                onChange={(event) =>
                  setForm((current) => ({ ...current, description: event.target.value }))
                }
                placeholder="这个 Agent 用来做什么"
                rows={2}
              />
            </Field>

            <Field>
              <FieldLabel htmlFor="agent-prompt-template">提示词模板</FieldLabel>
              <Textarea
                id="agent-prompt-template"
                value={form.prompt_template}
                onChange={(event) =>
                  setForm((current) => ({ ...current, prompt_template: event.target.value }))
                }
                placeholder="发送给模型的系统提示词"
                rows={6}
                className="font-mono text-xs"
              />
            </Field>

            <Field orientation="horizontal" className="items-center justify-between">
              <FieldLabel htmlFor="agent-enabled">启用 Agent</FieldLabel>
              <Switch
                id="agent-enabled"
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
              <Field>
                <FieldLabel htmlFor="agent-processor-config">处理器配置（JSON，可选）</FieldLabel>
                <Textarea
                  id="agent-processor-config"
                  value={form.processor_config}
                  onChange={(event) =>
                    setForm((current) => ({ ...current, processor_config: event.target.value }))
                  }
                  placeholder='{"temperature": 0.3}'
                  rows={4}
                  className="font-mono text-xs"
                />
                <FieldDescription>传给处理器的额外参数，留空表示使用默认配置。</FieldDescription>
              </Field>
            </div>
          </details>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              {pending ? '保存中…' : mode === 'create' ? '创建 Agent' : '保存更改'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
