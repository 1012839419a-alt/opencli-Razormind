'use client'

import {
  ArrowLeft,
  BarChart3,
  Braces,
  Database,
  Download,
  ExternalLink,
  FileStack,
  FileSpreadsheet,
  Filter,
  Rows3,
  Search,
  SlidersHorizontal,
  Upload,
  Workflow,
} from 'lucide-react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { use, useCallback, useEffect, useMemo, useState } from 'react'
import * as XLSX from 'xlsx'
import { toast } from 'sonner'

import { EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { PageContainer } from '@/components/shell/page-container'
import { ProjectNavigation } from '@/components/studio/project-navigation'
import { Badge } from '@/components/ui/badge'
import { Button, buttonVariants } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import { Input } from '@/components/ui/input'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { listRecords } from '@/lib/api/endpoints'
import { useProjectWorkflows, useRecords, useWorkspaceProjects } from '@/lib/api/hooks'
import type { CollectedRecord } from '@/lib/api/types'
import { formatDateTime, formatFreshness, formatRelative, formatSourceDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 50
const EXPORT_PAGE_SIZE = 100
const PRIORITY_FIELDS = ['title', 'name', 'url', 'text', 'content', 'author', 'published_at', 'source']
const SOURCE_PUBLISHED_RAW_KEYS = ['displayTime', 'published_at', 'publishedAt', 'published', 'sent_at', 'sentAt', 'time', 'timestamp'] as const
const SOURCE_PUBLISHED_FALLBACK_KEYS = ['noticeDate', 'date', 'created_at', 'createdAt', 'listed', 'updated'] as const
type WorkbenchView = 'dataset' | 'profile' | 'files'
type ExportFormat = 'xlsx' | 'csv' | 'json'

function recordPayload(record: CollectedRecord) {
  return Object.keys(record.normalized_data ?? {}).length ? record.normalized_data : record.raw_data
}

function recordTitle(record: CollectedRecord) {
  const payload = recordPayload(record)
  const value = payload.title ?? payload.name ?? payload.text ?? payload.content ?? payload.url
  return typeof value === 'string' && value.trim() ? value : `记录 ${record.id.slice(0, 8)}`
}

function sourceString(payload: Record<string, unknown>, key: string) {
  const value = payload[key]
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function recordSourcePublishedAt(record: CollectedRecord) {
  for (const key of SOURCE_PUBLISHED_RAW_KEYS) {
    const value = sourceString(record.raw_data, key)
    if (value) return value
  }
  const normalized = sourceString(record.normalized_data, 'published_at')
  if (normalized) return normalized
  for (const key of SOURCE_PUBLISHED_FALLBACK_KEYS) {
    const value = sourceString(record.raw_data, key)
    if (value) return value
  }
  return null
}

function formatCell(value: unknown) {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'string') return value
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return JSON.stringify(value)
}

function fieldKind(values: unknown[]) {
  const sample = values.find((value) => value !== null && value !== undefined && value !== '')
  if (sample === undefined) return 'empty'
  if (Array.isArray(sample)) return 'array'
  if (typeof sample === 'object') return 'object'
  return typeof sample
}

function collectRecordFields(records: CollectedRecord[], limit?: number) {
  const keys = new Set<string>()
  records.forEach((record) => Object.keys(recordPayload(record)).forEach((key) => keys.add(key)))
  const fields = [...keys]
    .filter((key) => !key.startsWith('_'))
    .sort((left, right) => {
      const leftIndex = PRIORITY_FIELDS.indexOf(left)
      const rightIndex = PRIORITY_FIELDS.indexOf(right)
      if (leftIndex >= 0 || rightIndex >= 0) {
        if (leftIndex < 0) return 1
        if (rightIndex < 0) return -1
        return leftIndex - rightIndex
      }
      return left.localeCompare(right)
    })
  return limit === undefined ? fields : fields.slice(0, limit)
}

function downloadBlob(filename: string, content: BlobPart, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function exportRow(record: CollectedRecord, fields: string[]): Record<string, string> {
  const payload = recordPayload(record)
  return {
    ...Object.fromEntries(fields.map((field) => [field, formatCell(payload[field])])),
    record_id: record.id,
    status: record.status,
    source_id: record.source_id,
    workflow_id: record.workflow_id ?? '',
    workflow_run_id: record.workflow_run_id ?? '',
    collected_at: record.created_at,
    updated_at: record.updated_at,
  }
}

function exportFileBase(projectName?: string) {
  const safeName = (projectName ?? 'project-data').trim().replace(/[^\p{L}\p{N}_-]+/gu, '-')
  return safeName.replace(/^-+|-+$/g, '') || 'project-data'
}

export default function ProjectDataWorkbenchPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = use(params)
  const searchParams = useSearchParams()
  const workspaceId = searchParams.get('workspace')
  const preferredWorkflowId = searchParams.get('workflow')
  const [view, setView] = useState<WorkbenchView>('dataset')
  const [search, setSearch] = useState(searchParams.get('search') ?? '')
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const [selectedField, setSelectedField] = useState<string | null>(null)
  const [selectedRecord, setSelectedRecord] = useState<CollectedRecord | null>(null)
  const [detailMode, setDetailMode] = useState<'normalized' | 'raw' | 'enrichment'>('normalized')
  const [selectedColumns, setSelectedColumns] = useState<string[] | null>(null)
  const [exporting, setExporting] = useState<ExportFormat | null>(null)

  const projectsQuery = useWorkspaceProjects(workspaceId)
  const workflowsQuery = useProjectWorkflows(workspaceId, projectId)
  const recordsQuery = useRecords({
    project_id: projectId,
    ...(status === 'all' ? {} : { status }),
    ...(search.trim() ? { search: search.trim() } : {}),
    page,
    limit: PAGE_SIZE,
  })
  const project = projectsQuery.data?.find((candidate) => candidate.id === projectId)
  const workflows = workflowsQuery.data ?? []
  const records = useMemo(() => recordsQuery.data?.data ?? [], [recordsQuery.data?.data])
  const meta = recordsQuery.data?.meta
  const total = meta?.total ?? records.length
  const pages = Math.max(1, meta?.pages ?? 1)
  const workflowId = preferredWorkflowId ?? project?.primary_workflow_id ?? workflows[0]?.id ?? null

  const visibleFields = useMemo(() => collectRecordFields(records, 24), [records])
  const tableFields = useMemo(() => {
    const fallback = visibleFields.slice(0, 4)
    if (selectedColumns === null) return fallback
    const selected = selectedColumns.filter((field) => visibleFields.includes(field))
    return selected.length ? selected : fallback.slice(0, 1)
  }, [selectedColumns, visibleFields])

  const activeField = selectedField && visibleFields.includes(selectedField) ? selectedField : visibleFields[0] ?? null
  const fieldProfiles = useMemo(() => visibleFields.map((field) => {
    const values = records.map((record) => recordPayload(record)[field])
    const filled = values.filter((value) => value !== null && value !== undefined && value !== '')
    const unique = new Set(filled.map((value) => JSON.stringify(value))).size
    return { field, kind: fieldKind(values), filled: filled.length, unique, ratio: records.length ? Math.round((filled.length / records.length) * 100) : 0 }
  }), [records, visibleFields])
  const activeProfile = fieldProfiles.find((profile) => profile.field === activeField) ?? null
  const valueDistribution = useMemo(() => {
    if (!activeField) return []
    const counts = new Map<string, number>()
    records.forEach((record) => {
      const label = formatCell(recordPayload(record)[activeField])
      counts.set(label, (counts.get(label) ?? 0) + 1)
    })
    return [...counts.entries()].sort((left, right) => right[1] - left[1]).slice(0, 8)
  }, [activeField, records])
  const sourceGroups = useMemo(() => {
    const groups = new Map<string, { count: number; updatedAt: string; statuses: Set<string> }>()
    records.forEach((record) => {
      const current = groups.get(record.source_id) ?? { count: 0, updatedAt: record.updated_at, statuses: new Set<string>() }
      current.count += 1
      current.statuses.add(record.status)
      if (record.updated_at > current.updatedAt) current.updatedAt = record.updated_at
      groups.set(record.source_id, current)
    })
    return [...groups.entries()].sort((left, right) => right[1].count - left[1].count)
  }, [records])

  useEffect(() => {
    setPage(1)
    setSelectedRecord(null)
  }, [search, status])

  const loading = projectsQuery.isLoading || workflowsQuery.isLoading || recordsQuery.isLoading
  const error = projectsQuery.error || workflowsQuery.error || recordsQuery.error
  const orchestrationHref = workspaceId && workflowId
    ? `/studio/workflow?workspace=${workspaceId}&project=${projectId}&workflow=${workflowId}`
    : null
  const overviewHref = workspaceId ? `/studio/projects/${projectId}?workspace=${workspaceId}` : '/studio'

  const toggleColumn = useCallback((field: string) => {
    setSelectedColumns((current) => {
      const active = current ?? visibleFields.slice(0, 4)
      if (active.includes(field)) {
        return active.length > 1 ? active.filter((candidate) => candidate !== field) : active
      }
      return [...active, field]
    })
  }, [visibleFields])

  const exportData = useCallback(async (format: ExportFormat) => {
    setExporting(format)
    try {
      const filters = {
        project_id: projectId,
        ...(status === 'all' ? {} : { status }),
        ...(search.trim() ? { search: search.trim() } : {}),
      }
      const allRecords: CollectedRecord[] = []
      let exportPage = 1
      while (true) {
        const response = await listRecords({ ...filters, page: exportPage, limit: EXPORT_PAGE_SIZE })
        allRecords.push(...response.data)
        if (!response.meta || exportPage >= response.meta.pages || response.data.length === 0) break
        exportPage += 1
      }
      if (allRecords.length === 0) {
        toast.info('当前筛选条件没有可导出的数据')
        return
      }
      const fields = collectRecordFields(allRecords)
      const rows = allRecords.map((record) => exportRow(record, fields))
      const base = exportFileBase(project?.name)
      if (format === 'json') {
        downloadBlob(`${base}.json`, JSON.stringify(allRecords, null, 2), 'application/json;charset=utf-8')
      } else if (format === 'csv') {
        const headers = Object.keys(rows[0])
        const csv = [headers, ...rows.map((row) => headers.map((header) => row[header] ?? ''))]
          .map((row) => row.map((value) => {
            const text = String(value)
            return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
          }).join(','))
          .join('\r\n')
        downloadBlob(`${base}.csv`, `\uFEFF${csv}`, 'text/csv;charset=utf-8')
      } else {
        const worksheet = XLSX.utils.json_to_sheet(rows)
        const workbook = XLSX.utils.book_new()
        XLSX.utils.book_append_sheet(workbook, worksheet, '数据集')
        const content = XLSX.write(workbook, { bookType: 'xlsx', type: 'array' })
        downloadBlob(`${base}.xlsx`, content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
      }
      toast.success(`已导出 ${allRecords.length} 条记录`)
    } catch (reason) {
      toast.error(reason instanceof Error ? `导出失败：${reason.message}` : '导出失败')
    } finally {
      setExporting(null)
    }
  }, [project, projectId, search, status])

  return (
    <PageContainer
      eyebrow="Project data workbench"
      title={project ? `${project.name} · 数据工作台` : '项目数据工作台'}
      description="用同一份项目真实数据完成浏览、字段剖析与输入追溯，并反向定位产生它的工作流。"
      className="max-w-none"
      actions={<Link href={overviewHref} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'min-h-11')}><ArrowLeft className="size-4" />返回项目</Link>}
    >
      <div className="border-b pb-3">
        <ProjectNavigation active="data" workspaceId={workspaceId} projectId={projectId} workflowId={workflowId} />
      </div>

      <section className="grid gap-3 sm:grid-cols-3" aria-label="项目数据摘要">
        <Summary label="项目记录" value={total.toLocaleString('zh-CN')} icon={Database} />
        <Summary label="当前页字段" value={String(visibleFields.length)} icon={Rows3} />
        <Summary label="当前页来源" value={String(sourceGroups.length)} icon={FileStack} />
      </section>

      <section className="overflow-hidden rounded-xl border bg-card">
        <header className="border-b">
          <div className="flex flex-wrap items-center justify-between gap-3 px-3 pt-3">
            <div className="flex rounded-lg border bg-muted/30 p-1" aria-label="数据工作台视图">
              <ViewButton active={view === 'dataset'} icon={Database} onClick={() => setView('dataset')}>数据集</ViewButton>
              <ViewButton active={view === 'profile'} icon={BarChart3} onClick={() => setView('profile')}>字段分析</ViewButton>
              <ViewButton active={view === 'files'} icon={FileStack} onClick={() => setView('files')}>项目文件</ViewButton>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {view === 'dataset' ? (
                <DropdownMenu>
                  <DropdownMenuTrigger render={<Button variant="outline" size="sm" className="min-h-10" disabled={Boolean(exporting) || records.length === 0} />}>
                    <Download className="size-4" />{exporting ? '导出中…' : '导出数据'}
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" className="w-64">
                    <DropdownMenuLabel>导出当前筛选结果（全量）</DropdownMenuLabel>
                    <DropdownMenuItem onClick={() => void exportData('xlsx')}><FileSpreadsheet className="size-4" />Excel 工作簿（.xlsx）</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportData('csv')}><Download className="size-4" />CSV（Excel 可打开）</DropdownMenuItem>
                    <DropdownMenuItem onClick={() => void exportData('json')}><Braces className="size-4" />JSON（保留完整结构）</DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
              {orchestrationHref ? <Link href={orchestrationHref} className={cn(buttonVariants({ variant: 'outline', size: 'sm' }), 'min-h-10')}><Workflow className="size-4" />打开业务编排</Link> : null}
            </div>
          </div>
          {view !== 'files' ? (
            <div className="grid gap-3 p-3 lg:grid-cols-[minmax(0,1fr)_13rem_auto] lg:items-center">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索标题、正文、URL 或字段值…" className="pl-9" />
              </div>
              <Select value={status} onValueChange={(value) => setStatus(value ?? 'all')}>
                <SelectTrigger><Filter className="size-4" /><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">全部处理状态</SelectItem>
                  <SelectItem value="raw">原始数据</SelectItem>
                  <SelectItem value="normalized">已标准化</SelectItem>
                  <SelectItem value="ai_processed">已富化</SelectItem>
                  <SelectItem value="notified">已交付</SelectItem>
                  <SelectItem value="error">处理失败</SelectItem>
                </SelectContent>
              </Select>
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="flex items-center gap-2"><SlidersHorizontal className="size-3.5" />当前视图使用项目过滤条件</span>
                {view === 'dataset' ? <ColumnPicker fields={visibleFields} selectedFields={tableFields} onToggle={toggleColumn} onReset={() => setSelectedColumns(null)} /> : null}
              </div>
            </div>
          ) : null}
        </header>

        {loading ? <div className="p-5"><LoadingState rows={7} /></div> : error ? (
          <div className="p-5"><ErrorState message={error instanceof Error ? error.message : '项目数据读取失败'} hint="确认后端、工作区和项目上下文可用。" /></div>
        ) : view === 'profile' ? (
          <FieldProfileView profiles={fieldProfiles} activeField={activeField} activeProfile={activeProfile} distribution={valueDistribution} total={records.length} onSelect={setSelectedField} />
        ) : view === 'files' ? (
          <ProjectInputsView groups={sourceGroups} />
        ) : records.length === 0 ? (
          <EmptyState title="项目还没有可显示的数据" description="运行并完成业务工作流后，记录会按 workflow_id 自动归入当前项目。" />
        ) : (
          <DatasetView records={records} visibleFields={tableFields} onSelect={setSelectedRecord} />
        )}

        {view !== 'files' ? (
          <footer className="flex flex-wrap items-center justify-between gap-3 border-t px-4 py-3 text-xs text-muted-foreground">
            <span>当前加载第 {page} / {pages} 页 · 共 {total.toLocaleString('zh-CN')} 条</span>
            <div className="flex gap-2"><Button size="sm" variant="outline" disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))}>上一页</Button><Button size="sm" variant="outline" disabled={page >= pages} onClick={() => setPage((value) => Math.min(pages, value + 1))}>下一页</Button></div>
          </footer>
        ) : null}
      </section>

      <Sheet open={Boolean(selectedRecord)} onOpenChange={(open) => !open && setSelectedRecord(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-2xl">
          {selectedRecord ? <>
            <SheetHeader><SheetTitle>{recordTitle(selectedRecord)}</SheetTitle><SheetDescription>对照原始输入、标准化结果和 AI 富化字段；这些内容是可审计的数据处理结果。</SheetDescription></SheetHeader>
            <div className="mt-5 flex flex-wrap gap-2">{(['normalized', 'raw', 'enrichment'] as const).map((mode) => <Button key={mode} size="sm" variant={detailMode === mode ? 'default' : 'outline'} onClick={() => setDetailMode(mode)}>{mode === 'normalized' ? '标准化结果' : mode === 'raw' ? '原始输入' : 'AI 富化'}</Button>)}</div>
            <pre className="mt-3 max-h-[55vh] overflow-auto rounded-lg border bg-muted/30 p-4 font-mono text-xs leading-5">{JSON.stringify(detailMode === 'normalized' ? selectedRecord.normalized_data : detailMode === 'raw' ? selectedRecord.raw_data : selectedRecord.ai_enrichment ?? {}, null, 2)}</pre>
            <div className="mt-4 grid gap-3 rounded-lg border p-4 text-xs sm:grid-cols-2"><Meta label="源发布时间" value={formatSourceDateTime(recordSourcePublishedAt(selectedRecord))} /><Meta label="数据新鲜度" value={formatFreshness(recordSourcePublishedAt(selectedRecord))} /><Meta label="采集时间" value={formatDateTime(selectedRecord.created_at)} /><Meta label="工作流" value={selectedRecord.workflow_id ?? '未绑定'} /><Meta label="运行" value={selectedRecord.workflow_run_id ?? '未绑定'} /><Meta label="来源" value={selectedRecord.source_id} /><Meta label="内容哈希" value={selectedRecord.content_hash} /></div>
            <div className="mt-4 flex flex-wrap gap-2">
              {workspaceId && selectedRecord.workflow_id ? <Link href={`/studio/workflow?workspace=${workspaceId}&project=${projectId}&workflow=${selectedRecord.workflow_id}`} className={buttonVariants({ variant: 'outline' })}><Workflow className="size-4" />定位业务编排</Link> : null}
              {workspaceId ? <Link href={`/studio/projects/${projectId}/evidence?workspace=${workspaceId}${selectedRecord.workflow_id ? `&workflow=${selectedRecord.workflow_id}` : ''}&record=${selectedRecord.id}`} className={buttonVariants({ variant: 'outline' })}><ExternalLink className="size-4" />查看逻辑与证据</Link> : null}
            </div>
          </> : null}
        </SheetContent>
      </Sheet>
    </PageContainer>
  )
}

function ViewButton({ active, children, icon: Icon, onClick }: { active: boolean; children: React.ReactNode; icon: typeof Database; onClick: () => void }) {
  return <button type="button" aria-pressed={active} onClick={onClick} className={cn('flex min-h-9 items-center gap-2 rounded-md px-3 text-xs transition-colors', active ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}><Icon className="size-3.5" />{children}</button>
}

function ColumnPicker({ fields, selectedFields, onToggle, onReset }: { fields: string[]; selectedFields: string[]; onToggle: (field: string) => void; onReset: () => void }) {
  return <DropdownMenu>
    <DropdownMenuTrigger render={<Button variant="ghost" size="sm" className="min-h-8 gap-1.5 px-2 text-xs" disabled={fields.length === 0} />}>
      <SlidersHorizontal className="size-3.5" />列管理
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="w-64">
      <DropdownMenuLabel>显示字段（至少保留 1 列）</DropdownMenuLabel>
      {fields.map((field) => <DropdownMenuCheckboxItem key={field} checked={selectedFields.includes(field)} onCheckedChange={() => onToggle(field)}>{field}</DropdownMenuCheckboxItem>)}
      <DropdownMenuSeparator />
      <DropdownMenuItem onClick={onReset}>恢复默认列</DropdownMenuItem>
    </DropdownMenuContent>
  </DropdownMenu>
}

function DatasetView({ records, visibleFields, onSelect }: { records: CollectedRecord[]; visibleFields: string[]; onSelect: (record: CollectedRecord) => void }) {
  return <div className="overflow-x-auto"><Table><TableHeader><TableRow><TableHead className="min-w-64">记录</TableHead>{visibleFields.slice(0, 4).map((field) => <TableHead key={field} className="min-w-40">{field}</TableHead>)}<TableHead>状态</TableHead><TableHead>源发布时间</TableHead></TableRow></TableHeader><TableBody>{records.map((record) => { const payload = recordPayload(record); const sourcePublishedAt = recordSourcePublishedAt(record); return <TableRow key={record.id} className="cursor-pointer" onClick={() => onSelect(record)}><TableCell><div className="max-w-80"><div className="truncate font-medium">{recordTitle(record)}</div><div className="mt-1 truncate font-mono text-[10px] text-muted-foreground">{record.id}</div></div></TableCell>{visibleFields.slice(0, 4).map((field) => <TableCell key={field}><span className="block max-w-64 truncate text-xs text-muted-foreground">{formatCell(payload[field])}</span></TableCell>)}<TableCell><Badge variant={record.status === 'error' ? 'destructive' : 'outline'}>{record.status}</Badge></TableCell><TableCell className="whitespace-nowrap text-xs text-muted-foreground" title={formatSourceDateTime(sourcePublishedAt)}><span className="block text-foreground/80">{formatFreshness(sourcePublishedAt)}</span><span className="mt-0.5 block text-[10px]">{formatSourceDateTime(sourcePublishedAt)}</span></TableCell></TableRow> })}</TableBody></Table></div>
}

function FieldProfileView({ profiles, activeField, activeProfile, distribution, total, onSelect }: { profiles: Array<{ field: string; kind: string; filled: number; unique: number; ratio: number }>; activeField: string | null; activeProfile: { field: string; kind: string; filled: number; unique: number; ratio: number } | null; distribution: Array<[string, number]>; total: number; onSelect: (field: string) => void }) {
  const max = Math.max(1, ...distribution.map(([, count]) => count))
  return <div className="grid min-h-[32rem] lg:grid-cols-[16rem_minmax(0,1fr)]"><aside className="border-b p-3 lg:border-b-0 lg:border-r"><p className="px-2 pb-2 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">字段 · {profiles.length}</p><div className="max-h-[30rem] space-y-1 overflow-y-auto">{profiles.map((profile) => <button type="button" key={profile.field} onClick={() => onSelect(profile.field)} className={cn('flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-2 text-left text-xs', activeField === profile.field ? 'bg-muted text-foreground' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground')}><span className="truncate font-mono">{profile.field}</span><span>{profile.ratio}%</span></button>)}</div></aside><div className="p-5">{activeProfile ? <><div className="flex flex-wrap items-start justify-between gap-3"><div><div className="flex items-center gap-2"><Braces className="size-4 text-muted-foreground" /><h2 className="font-mono text-base font-semibold">{activeProfile.field}</h2></div><p className="mt-1 text-xs text-muted-foreground">按当前加载页即时计算，不写回源数据。</p></div><Badge variant="outline">{activeProfile.kind}</Badge></div><div className="mt-5 grid gap-3 sm:grid-cols-3"><Fact label="字段填充" value={`${activeProfile.filled} / ${total}`} /><Fact label="完整率" value={`${activeProfile.ratio}%`} /><Fact label="唯一值" value={String(activeProfile.unique)} /></div><section className="mt-6"><div className="flex items-center justify-between"><p className="text-xs font-medium">值分布</p><span className="text-[10px] text-muted-foreground">Top {distribution.length}</span></div><div className="mt-3 space-y-3">{distribution.map(([label, count]) => <div key={label} className="grid grid-cols-[minmax(8rem,15rem)_minmax(0,1fr)_3rem] items-center gap-3 text-xs"><span className="truncate font-mono text-muted-foreground" title={label}>{label}</span><span className="h-2 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(4, (count / max) * 100)}%` }} /></span><span className="text-right font-mono">{count}</span></div>)}</div></section></> : <p className="text-sm text-muted-foreground">当前数据没有可分析字段。</p>}</div></div>
}

function ProjectInputsView({ groups }: { groups: Array<[string, { count: number; updatedAt: string; statuses: Set<string> }]> }) {
  return <div className="p-5"><div className="flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold">项目输入与处理批次</h2><p className="mt-1 text-xs text-muted-foreground">先用现有来源记录验证文件工作台结构；上传与解析引擎接线后仍沿用这里的项目上下文。</p></div><Button variant="outline" size="sm" disabled title="文件上传适配器尚未接入"><Upload className="size-4" />上传文件 · 接入中</Button></div><div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{groups.map(([sourceId, group]) => <article key={sourceId} className="rounded-lg border p-4"><div className="flex items-start justify-between gap-3"><span className="grid size-9 place-items-center rounded-md bg-muted"><FileStack className="size-4 text-muted-foreground" /></span><Badge variant="outline">{group.count} 条</Badge></div><h3 className="mt-4 truncate font-mono text-xs font-medium" title={sourceId}>{sourceId}</h3><p className="mt-1 text-[11px] text-muted-foreground">最近处理 {formatRelative(group.updatedAt)}</p><div className="mt-3 flex flex-wrap gap-1.5">{[...group.statuses].map((status) => <Badge key={status} variant={status === 'error' ? 'destructive' : 'secondary'}>{status}</Badge>)}</div></article>)}</div></div>
}

function Summary({ label, value, icon: Icon }: { label: string; value: string; icon: typeof Database }) {
  return <div className="flex items-center gap-3 rounded-xl border bg-card p-4"><span className="grid size-10 place-items-center rounded-lg bg-muted"><Icon className="size-4 text-muted-foreground" /></span><div><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-mono text-xl font-semibold">{value}</p></div></div>
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-lg border p-3"><p className="text-[10px] text-muted-foreground">{label}</p><p className="mt-1 font-mono text-sm font-semibold">{value}</p></div> }
function Meta({ label, value }: { label: string; value: string }) { return <div><p className="text-muted-foreground">{label}</p><p className="mt-1 break-all font-mono text-[11px]">{value}</p></div> }
