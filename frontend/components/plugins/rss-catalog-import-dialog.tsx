'use client'

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { toast } from 'sonner'

import * as api from '@/lib/api/endpoints'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

export function RssCatalogImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [catalogUrl, setCatalogUrl] = useState('')
  const queryClient = useQueryClient()

  const importCatalog = useMutation({
    mutationFn: () => api.importRssCatalog(catalogUrl.trim()),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['sources'] })
      toast.success(`已导入 ${result.created.length} 个订阅，跳过 ${result.skipped_existing.length} 个重复项`)
      setCatalogUrl('')
      onOpenChange(false)
    },
    onError: (error: Error) => toast.error(error.message),
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>导入 OPML 订阅清单</DialogTitle>
          <DialogDescription>
            粘贴你自己的 OPML 地址，批量创建 RSS 数据源。所有条目默认停用，确认后再进入工作流采集。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-2 py-2">
          <Label htmlFor="rss-catalog-url">公开 OPML 地址</Label>
          <Input
            id="rss-catalog-url"
            value={catalogUrl}
            onChange={(event) => setCatalogUrl(event.target.value)}
            placeholder="https://example.com/subscriptions.opml"
            inputMode="url"
          />
          <p className="text-xs leading-5 text-muted-foreground">
            这是一项可选的批量导入能力，不会把公共来源包写死在系统里。单次文件上限 2 MB。
          </p>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            className="gap-1.5"
            disabled={!catalogUrl.trim() || importCatalog.isPending}
            onClick={() => importCatalog.mutate()}
          >
            <Download className="size-3.5" />
            {importCatalog.isPending ? '正在导入…' : '导入订阅清单'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
