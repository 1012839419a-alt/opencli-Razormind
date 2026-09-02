'use client'

import { Globe } from 'lucide-react'

// Read-only status view for the ops dashboard (part of the System/ops slice —
// WIRING_GAP_LEDGER W5). Instance management (add/remove/reconfigure via
// addChromeInstance/updateChromeInstanceConfig/removeChromeInstance) is a
// separate slice living on /browsers; this card and that page share the
// same ['chrome-pool'] query key/hook (useChromePool) by design so either
// side's mutations keep both views in sync.
import { useChromePool } from '@/lib/api/hooks'
import { BACKEND_HINT, EmptyState, ErrorState, LoadingState } from '@/components/shell/data-states'
import { StatusBadge } from '@/components/shell/status-badge'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'

export function ChromePoolCard() {
  const { data, isLoading, isError, error } = useChromePool()
  const endpoints = data?.endpoints ?? []

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-sm">
          <Globe className="size-4" /> Chrome 浏览器池
        </CardTitle>
        <CardDescription>
          {data ? `共 ${data.total} 个实例，${data.available} 个当前可用` : '代理池中浏览器实例的运行状态'}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex-1">
        {isLoading ? (
          <LoadingState rows={2} />
        ) : isError ? (
          <ErrorState message={(error as Error)?.message} hint={BACKEND_HINT} />
        ) : endpoints.length === 0 ? (
          <EmptyState title="暂无浏览器实例" description="代理池中还没有注册任何 Chrome 实例。" />
        ) : (
          <div className="overflow-hidden rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>端点</TableHead>
                  <TableHead>状态</TableHead>
                  <TableHead>模式</TableHead>
                  <TableHead>会话类型</TableHead>
                  <TableHead>容器</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {endpoints.map((ep) => (
                  <TableRow key={ep.url}>
                    <TableCell className="max-w-40 truncate font-mono text-xs" title={ep.url}>
                      {ep.url}
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={ep.available ? 'online' : 'offline'} />
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary">{ep.mode.toUpperCase()}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={ep.profile_kind === 'anonymous' ? 'outline' : 'secondary'}>
                        {ep.profile_kind === 'anonymous' ? '匿名' : '已登录会话'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {ep.container_status ?? '未知'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
