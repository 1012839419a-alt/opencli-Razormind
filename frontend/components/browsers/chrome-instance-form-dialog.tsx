'use client'

import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { useAddChromeInstance, useUpdateChromeInstanceConfig } from '@/lib/api/hooks'
import type { ChromeEndpoint } from '@/lib/api/types'
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

const MODE_OPTIONS: { value: 'bridge' | 'cdp'; label: string; description: string }[] = [
  {
    value: 'bridge',
    label: 'Bridge',
    description: '通过 OpenCLI 浏览器扩展桥接采集，适合需要登录态的站点。',
  },
  {
    value: 'cdp',
    label: 'CDP',
    description: '通过 Chrome DevTools Protocol 直连，适合无需登录态的轻量采集。',
  },
]

interface FormState {
  count: number
  mode: 'bridge' | 'cdp'
  useAgent: boolean
  agentUrl: string
  agentProtocol: 'http' | 'ws'
}

const EMPTY_FORM: FormState = {
  count: 1,
  mode: 'bridge',
  useAgent: false,
  agentUrl: '',
  agentProtocol: 'http',
}

function instanceToForm(instance: ChromeEndpoint): FormState {
  return {
    count: 1,
    mode: instance.mode,
    useAgent: Boolean(instance.agent_url),
    agentUrl: instance.agent_url ?? '',
    agentProtocol: instance.agent_protocol === 'ws' ? 'ws' : 'http',
  }
}

export function ChromeInstanceFormDialog({
  mode,
  instance,
  triggerLabel,
  triggerIcon,
  triggerVariant = 'default',
  triggerSize = 'sm',
}: {
  mode: 'create' | 'edit'
  /** Required when mode === 'edit'. */
  instance?: ChromeEndpoint
  triggerLabel: string
  triggerIcon?: React.ReactNode
  triggerVariant?: React.ComponentProps<typeof Button>['variant']
  triggerSize?: React.ComponentProps<typeof Button>['size']
}) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<FormState>(() => (instance ? instanceToForm(instance) : EMPTY_FORM))
  const addMutation = useAddChromeInstance()
  const updateMutation = useUpdateChromeInstanceConfig()
  const pending = addMutation.isPending || updateMutation.isPending

  useEffect(() => {
    if (!open) return
    setForm(instance ? instanceToForm(instance) : EMPTY_FORM)
  }, [open, instance])

  const finish = (message: string) => {
    toast.success(message)
    setOpen(false)
  }
  const onError = (error: Error) => toast.error(error.message)

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (form.useAgent && !form.agentUrl.trim()) {
      toast.error('已开启远程 Agent 路由，请填写 Agent 地址')
      return
    }

    if (mode === 'create') {
      addMutation.mutate(
        {
          count: form.count,
          mode: form.mode,
          agent_url: form.useAgent ? form.agentUrl.trim() : '',
          agent_protocol: form.useAgent ? form.agentProtocol : '',
        },
        {
          onSuccess: (result) => finish(`已添加 ${result.created.length} 个 Chrome 实例`),
          onError,
        },
      )
      return
    }

    if (instance) {
      updateMutation.mutate(
        {
          endpoint: instance.url,
          data: {
            mode: form.mode,
            agent_url: form.useAgent ? form.agentUrl.trim() : null,
            agent_protocol: form.useAgent ? form.agentProtocol : null,
          },
        },
        { onSuccess: () => finish('实例配置已更新'), onError },
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant={triggerVariant} size={triggerSize} />}>
        {triggerIcon}
        {triggerLabel}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{mode === 'create' ? '添加 Chrome 实例' : '编辑实例配置'}</DialogTitle>
            <DialogDescription>
              {mode === 'create'
                ? '在本机 Docker 中启动新的 Chrome 容器并加入采集池。'
                : `更新 ${instance?.url} 的连接模式与 Agent 路由。`}
            </DialogDescription>
          </DialogHeader>

          <FieldGroup className="gap-4">
            {mode === 'create' ? (
              <Field>
                <FieldLabel htmlFor="chrome-instance-count">实例数量</FieldLabel>
                <Input
                  id="chrome-instance-count"
                  type="number"
                  min={1}
                  max={10}
                  value={form.count}
                  onChange={(event) => {
                    const parsed = Number(event.target.value)
                    const clamped = Number.isFinite(parsed) ? Math.min(10, Math.max(1, parsed)) : 1
                    setForm((current) => ({ ...current, count: clamped }))
                  }}
                />
                <FieldDescription>一次最多启动 10 个新容器（agent-N 命名，端口自动分配）。</FieldDescription>
              </Field>
            ) : null}

            <Field>
              <FieldLabel htmlFor="chrome-instance-mode">连接模式</FieldLabel>
              <Select
                value={form.mode}
                onValueChange={(value) =>
                  setForm((current) => ({ ...current, mode: (value as 'bridge' | 'cdp') ?? 'bridge' }))
                }
              >
                <SelectTrigger id="chrome-instance-mode" className="w-full">
                  <SelectValue placeholder="选择模式">
                    {MODE_OPTIONS.find((option) => option.value === form.mode)?.label}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {MODE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldDescription>
                {MODE_OPTIONS.find((option) => option.value === form.mode)?.description}
              </FieldDescription>
            </Field>

            <Field>
              <div className="flex items-center justify-between gap-3">
                <FieldLabel htmlFor="chrome-instance-use-agent">通过远程 Agent 路由</FieldLabel>
                <Switch
                  id="chrome-instance-use-agent"
                  checked={form.useAgent}
                  onCheckedChange={(checked) => setForm((current) => ({ ...current, useAgent: checked }))}
                />
              </div>
              <FieldDescription>
                默认使用本机采集池；开启后由指定的远程 Agent 代理该实例的浏览器动作。
              </FieldDescription>
            </Field>

            {form.useAgent ? (
              <>
                <Field>
                  <FieldLabel htmlFor="chrome-instance-agent-url">Agent 地址</FieldLabel>
                  <Input
                    id="chrome-instance-agent-url"
                    placeholder="http://192.168.1.100:19823"
                    value={form.agentUrl}
                    onChange={(event) => setForm((current) => ({ ...current, agentUrl: event.target.value }))}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="chrome-instance-agent-protocol">Agent 通道</FieldLabel>
                  <Select
                    value={form.agentProtocol}
                    onValueChange={(value) =>
                      setForm((current) => ({
                        ...current,
                        agentProtocol: (value as 'http' | 'ws') ?? 'http',
                      }))
                    }
                  >
                    <SelectTrigger id="chrome-instance-agent-protocol" className="w-full">
                      <SelectValue placeholder="选择通道">
                        {form.agentProtocol === 'ws' ? 'WS（反向连接）' : 'HTTP（轮询）'}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="http">HTTP（轮询）</SelectItem>
                      <SelectItem value="ws">WS（反向连接，适合 NAT 内网）</SelectItem>
                    </SelectContent>
                  </Select>
                </Field>
              </>
            ) : null}
          </FieldGroup>

          <DialogFooter>
            <Button type="submit" disabled={pending} className="min-w-24">
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              {mode === 'create' ? '添加' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
