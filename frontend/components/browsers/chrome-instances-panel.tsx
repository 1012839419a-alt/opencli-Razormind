'use client'

import { useState } from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { useChromePool, useRemoveChromeInstance } from '@/lib/api/hooks'
import type { ChromeEndpoint } from '@/lib/api/types'
import { ChromeInstanceFormDialog } from '@/components/browsers/chrome-instance-form-dialog'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'

const MODE_LABEL: Record<string, string> = { bridge: 'Bridge', cdp: 'CDP' }
const PROFILE_KIND_LABEL: Record<string, string> = { anonymous: '匿名', authenticated: '已登录' }

/**
 * agent-N Docker container index for this endpoint, or null when it isn't a
 * locally Docker-managed container this UI can stop/remove (e.g. a raw CDP
 * endpoint registered via /browsers/cdp-endpoint, or a remote agent
 * registered via /browsers/agents/register or the WS channel). Mirrors the
 * hostname convention backend/api/v1/workers.py's _novnc_port already
 * relies on: agent → instance 1, agent-N → instance N.
 */
function agentContainerIndex(url: string): number | null {
  try {
    const hostname = new URL(url).hostname
    const match = /^agent(?:-(\d+))?$/.exec(hostname)
    if (!match) return null
    return match[1] ? Number(match[1]) : 1
  } catch {
    return null
  }
}

export function ChromeInstancesPanel() {
  const { data, isLoading, isError, error } = useChromePool()
  const endpoints = data?.endpoints ?? []
  const [confirmRemoveUrl, setConfirmRemoveUrl] = useState<string | null>(null)
  const removeMutation = useRemoveChromeInstance()

  const handleRemove = (endpoint: ChromeEndpoint) => {
    const n = agentContainerIndex(endpoint.url)
    if (n === null || n < 2) return
    if (confirmRemoveUrl !== endpoint.url) {
      setConfirmRemoveUrl(endpoint.url)
      return
    }
    removeMutation.mutate(n, {
      onSuccess: () => {
        toast.success(`已移除 agent-${n}`)
        setConfirmRemoveUrl(null)
      },
      onError: (cause: Error) => toast.error(cause.message),
    })
  }

  return (
    <Card className="overflow-hidden py-0">
      <CardHeader className="border-b bg-muted/20 py-4">
        <CardTitle className="text-base">Chrome 实例</CardTitle>
        <CardDescription>
          本机 Docker 采集池，可选路由到远程 Agent。移除操作仅支持 Docker 管理的 agent-2 及以后实例。
        </CardDescription>
        <CardAction>
          <ChromeInstanceFormDialog mode="create" triggerLabel="添加实例" triggerIcon={<Plus className="size-4" />} />
        </CardAction>
      </CardHeader>
      <CardContent className="p-4">
        {isLoading ? (
          <LoadingState />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        ) : endpoints.length === 0 ? (
          <EmptyState title="暂无 Chrome 实例" description="添加一个实例后即可用于浏览器采集。" />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>地址</TableHead>
                <TableHead>模式</TableHead>
                <TableHead>Agent 路由</TableHead>
                <TableHead>登录态</TableHead>
                <TableHead>可用</TableHead>
                <TableHead>容器状态</TableHead>
                <TableHead className="text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {endpoints.map((endpoint) => {
                const n = agentContainerIndex(endpoint.url)
                const removable = n !== null && n >= 2
                const confirming = confirmRemoveUrl === endpoint.url
                return (
                  <TableRow key={endpoint.url}>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      <div className="flex flex-col">
                        <span>{endpoint.url}</span>
                        <span className="text-muted-foreground/70">noVNC :{endpoint.novnc_port}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{MODE_LABEL[endpoint.mode] ?? endpoint.mode}</Badge>
                    </TableCell>
                    <TableCell className="text-xs">
                      {endpoint.agent_url ? (
                        <span className="font-mono text-muted-foreground">
                          {endpoint.agent_url} · {endpoint.agent_protocol?.toUpperCase()}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">本地</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {PROFILE_KIND_LABEL[endpoint.profile_kind ?? ''] ?? endpoint.profile_kind ?? '未知'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={endpoint.available ? 'online' : 'offline'} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={endpoint.container_status} />
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <ChromeInstanceFormDialog
                          mode="edit"
                          instance={endpoint}
                          triggerLabel="编辑"
                          triggerIcon={<Pencil className="size-3" />}
                          triggerVariant="ghost"
                          triggerSize="xs"
                        />
                        <Button
                          size="xs"
                          variant={confirming ? 'destructive' : 'ghost'}
                          disabled={!removable || removeMutation.isPending}
                          onClick={() => handleRemove(endpoint)}
                          title={
                            removable
                              ? undefined
                              : 'agent-1 由 docker-compose 管理；非 Docker 管理的实例（CDP 直连 / 远程注册的 Agent）暂不支持从此处移除'
                          }
                          className="gap-1"
                        >
                          <Trash2 className="size-3" />
                          {confirming ? '确认移除' : '移除'}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
