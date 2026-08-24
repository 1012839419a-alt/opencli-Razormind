'use client'

import { useState, type FormEvent } from 'react'
import { Loader2, Pencil, Plug, Plus, Table2, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import {
  useCreateDeliveryConnection,
  useDeleteDeliveryConnection,
  useDeliveryConnections,
  useProbeFeishuBitable,
  useUpdateDeliveryConnection,
} from '@/lib/api/hooks'
import type { DeliveryConnection, DeliveryConnectionInput } from '@/lib/api/types'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

function ConnectionDialog({ connection }: { connection?: DeliveryConnection }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(connection?.name ?? '飞书多维表格')
  const [appId, setAppId] = useState('')
  const [appSecret, setAppSecret] = useState('')
  const [enabled, setEnabled] = useState(connection?.enabled ?? true)
  const create = useCreateDeliveryConnection()
  const update = useUpdateDeliveryConnection()
  const pending = create.isPending || update.isPending

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const data: DeliveryConnectionInput = {
      name: name.trim(),
      ...(appId.trim() ? { app_id: appId.trim() } : {}),
      ...(appSecret ? { app_secret: appSecret } : {}),
      enabled,
    }
    const options = {
      onSuccess: () => {
        toast.success(connection ? '飞书连接已更新' : '飞书连接已保存')
        setOpen(false)
        setAppSecret('')
      },
      onError: (error: Error) => toast.error(error.message),
    }
    if (connection) update.mutate({ id: connection.id, data }, options)
    else create.mutate(data, options)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size={connection ? 'xs' : 'sm'} variant={connection ? 'ghost' : 'default'} />}>
        {connection ? <Pencil className="size-3" /> : <Plus className="size-4" />}
        {connection ? '编辑' : '添加飞书连接'}
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <form className="space-y-4" onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{connection ? '编辑飞书连接' : '连接飞书多维表格'}</DialogTitle>
            <DialogDescription>
              App Secret 只写入本机加密存储；工作流节点不会保存或读取明文凭据。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="feishu-name">名称</Label>
            <Input id="feishu-name" value={name} onChange={(event) => setName(event.target.value)} required />
          </div>
          <div className="space-y-2">
            <Label htmlFor="feishu-app-id">App ID</Label>
            <Input id="feishu-app-id" value={appId} onChange={(event) => setAppId(event.target.value)} placeholder={connection?.app_id_preview ?? 'cli_xxx'} required={!connection} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="feishu-app-secret">App Secret</Label>
            <Input id="feishu-app-secret" type="password" value={appSecret} onChange={(event) => setAppSecret(event.target.value)} placeholder={connection?.has_app_secret ? '留空则保留现有密钥' : 'App Secret'} required={!connection} autoComplete="new-password" />
          </div>
          <label className="flex items-center justify-between rounded-md border p-3 text-sm">
            <span>启用连接</span>
            <Switch checked={enabled} onCheckedChange={setEnabled} />
          </label>
          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              保存
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function TargetProbe({ connection }: { connection: DeliveryConnection }) {
  const [appToken, setAppToken] = useState('')
  const [tableId, setTableId] = useState('')
  const probe = useProbeFeishuBitable()
  return (
    <div className="grid gap-2 rounded-md border bg-muted/30 p-3 sm:grid-cols-[1fr_1fr_auto]">
      <Input value={appToken} onChange={(event) => setAppToken(event.target.value)} placeholder="Bitable App Token" />
      <Input value={tableId} onChange={(event) => setTableId(event.target.value)} placeholder="Table ID" />
      <Button
        size="sm"
        variant="outline"
        disabled={!appToken || !tableId || probe.isPending}
        onClick={() => probe.mutate({ id: connection.id, data: { app_token: appToken, table_id: tableId } }, {
          onSuccess: (result) => toast.success(`目标可用，读取到 ${result.field_count} 个字段`),
          onError: (error: Error) => toast.error(error.message),
        })}
      >
        {probe.isPending ? <Loader2 className="size-3 animate-spin" /> : <Plug className="size-3" />}
        验证目标
      </Button>
    </div>
  )
}

export function FeishuBitableConnectionPanel() {
  const query = useDeliveryConnections()
  const remove = useDeleteDeliveryConnection()
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  if (query.isLoading) return <LoadingState />
  if (query.isError) return <ErrorState message={(query.error as Error).message} hint={BACKEND_HINT} />
  const connections = query.data?.data ?? []
  return (
    <section className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">飞书多维表格连接</h2>
          <p className="mt-1 text-sm text-muted-foreground">管理可复用的本地投递凭据；具体 App、数据表和字段映射由工作流节点选择。</p>
        </div>
        <ConnectionDialog />
      </div>
      {connections.length === 0 ? <EmptyState title="暂无飞书连接" description="创建连接后，可在工作流中添加 Feishu Bitable Sink。" /> : (
        <div className="grid gap-3">
          {connections.map((connection) => (
            <Card key={connection.id}>
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3"><Table2 className="size-5 text-primary" /><div><CardTitle className="text-sm">{connection.name}</CardTitle><p className="mt-1 font-mono text-xs text-muted-foreground">App ID {connection.app_id_preview}</p></div></div>
                  <StatusBadge status={connection.enabled ? 'enabled' : 'disabled'} />
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <TargetProbe connection={connection} />
                <div className="flex gap-2">
                  <ConnectionDialog connection={connection} />
                  <Button size="xs" variant={confirmDelete === connection.id ? 'destructive' : 'ghost'} onClick={() => {
                    if (confirmDelete !== connection.id) return setConfirmDelete(connection.id)
                    remove.mutate(connection.id, { onSuccess: () => { toast.success('飞书连接已删除'); setConfirmDelete(null) }, onError: (error: Error) => toast.error(error.message) })
                  }}><Trash2 className="size-3" />{confirmDelete === connection.id ? '确认删除' : '删除'}</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </section>
  )
}
