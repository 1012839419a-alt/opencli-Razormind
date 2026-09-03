'use client'

import { useEffect, useState } from 'react'

import { useDeliveryConnections } from '@/lib/api/hooks'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { SectionCaption } from './inspector-shell'

export interface FeishuBitableTargetParams {
  connectionId?: string
  appToken?: string
  tableId?: string
  fieldMap?: Record<string, string>
}

export function FeishuBitableTargetEditor({
  params,
  onChange,
}: {
  params: FeishuBitableTargetParams
  onChange: (patch: Partial<FeishuBitableTargetParams>) => void
}) {
  const connectionsQuery = useDeliveryConnections()
  const connections = connectionsQuery.data?.data ?? []
  const [fieldMapText, setFieldMapText] = useState(() => JSON.stringify(params.fieldMap ?? {}, null, 2))
  const [fieldMapError, setFieldMapError] = useState<string | null>(null)

  useEffect(() => setFieldMapText(JSON.stringify(params.fieldMap ?? {}, null, 2)), [params.fieldMap])

  const updateFieldMap = (value: string) => {
    setFieldMapText(value)
    try {
      const parsed: unknown = JSON.parse(value)
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error()
      const entries = Object.entries(parsed as Record<string, unknown>)
      if (entries.some(([, target]) => typeof target !== 'string' || !target.trim())) throw new Error()
      setFieldMapError(null)
      onChange({ fieldMap: Object.fromEntries(entries) as Record<string, string> })
    } catch {
      setFieldMapError('请输入“来源字段路径 → 飞书列名”的 JSON 对象。')
    }
  }

  return (
    <section className="space-y-3 rounded-[3px] border border-[#35404b] bg-[#101216]/84 p-3">
      <div>
        <SectionCaption>飞书多维表格 / BITABLE TARGET</SectionCaption>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">节点只保存连接引用、目标 ID 和非敏感字段映射，不包含 App Secret。</p>
      </div>
      <div className="space-y-1.5">
        <Label className="font-mono text-[10px] uppercase">连接</Label>
        <select className="h-8 w-full rounded-md border bg-background px-2 text-xs" value={params.connectionId ?? ''} onChange={(event) => onChange({ connectionId: event.target.value })}>
          <option value="">选择已保存连接</option>
          {connections.filter((connection) => connection.enabled).map((connection) => <option key={connection.id} value={connection.id}>{connection.name} · {connection.app_id_preview}</option>)}
        </select>
        {connectionsQuery.isError ? <p className="text-[11px] text-destructive">连接列表读取失败，请前往 Provider 与连接检查后端。</p> : null}
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="space-y-1.5"><Label className="font-mono text-[10px] uppercase">App Token</Label><Input value={params.appToken ?? ''} onChange={(event) => onChange({ appToken: event.target.value })} placeholder="bascn..." /></div>
        <div className="space-y-1.5"><Label className="font-mono text-[10px] uppercase">Table ID</Label><Input value={params.tableId ?? ''} onChange={(event) => onChange({ tableId: event.target.value })} placeholder="tbl..." /></div>
      </div>
      <div className="space-y-1.5">
        <Label className="font-mono text-[10px] uppercase">字段映射 JSON</Label>
        <Textarea className="min-h-36 font-mono text-[11px]" value={fieldMapText} onChange={(event) => updateFieldMap(event.target.value)} />
        <p className={fieldMapError ? 'text-[11px] text-destructive' : 'text-[11px] text-muted-foreground'}>{fieldMapError ?? '必须保留 recordId、workflowRunId、evidenceDigest 三个身份字段。'}</p>
      </div>
    </section>
  )
}
