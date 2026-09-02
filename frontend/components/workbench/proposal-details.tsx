'use client'

import { useState } from 'react'
import { CheckCircle2, FileCode2 } from 'lucide-react'

import type { WorkbenchProposal } from '@/lib/api/types'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

type ProposalDetailsProps = {
  proposal: WorkbenchProposal
  onConfirm: () => void
  confirming: boolean
}

export function ProposalDetails({ proposal, onConfirm, confirming }: ProposalDetailsProps) {
  const [confirmationOpen, setConfirmationOpen] = useState(false)
  const statusClass = proposal.status === 'applied'
    ? 'border-emerald-500/40 text-emerald-700 dark:text-emerald-300'
    : 'border-amber-500/40 text-amber-700 dark:text-amber-300'

  return (
    <Card className="border-amber-500/30">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileCode2 className="size-4" />
              变更提案
            </CardTitle>
            <CardDescription>
              控制器检查点 {proposal.checkpointSha.slice(0, 12)} · 基础 {proposal.baseSha.slice(0, 12)}
            </CardDescription>
          </div>
          <Badge variant="outline" className={statusClass}>
            {proposal.status === 'pending_confirmation' ? '待确认' : proposal.status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {proposal.errorMessage ? (
          <p role="alert" className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
            {proposal.errorMessage}
          </p>
        ) : null}
        <div className="grid gap-4 md:grid-cols-2">
          <section>
            <h3 className="text-sm font-medium">修改文件</h3>
            {proposal.modifiedFiles.length ? (
              <ul className="mt-2 space-y-1 font-mono text-xs text-muted-foreground">
                {proposal.modifiedFiles.map((file) => <li key={file}>{file}</li>)}
              </ul>
            ) : <p className="mt-2 text-sm text-muted-foreground">没有文件清单。</p>}
          </section>
          <section>
            <h3 className="text-sm font-medium">测试证据</h3>
            {proposal.tests.length ? (
              <ul className="mt-2 space-y-2">
                {proposal.tests.map((test, index) => (
                  <li key={`${test.command}-${index}`} className="rounded-md border bg-muted/30 p-2 text-xs">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">{test.outcome}</Badge>
                      <code className="break-all">{test.command}</code>
                    </div>
                    {test.summary ? <p className="mt-1 text-muted-foreground">{test.summary}</p> : null}
                  </li>
                ))}
              </ul>
            ) : <p className="mt-2 text-sm text-muted-foreground">运行时没有报告结构化测试证据。</p>}
          </section>
        </div>
        <section>
          <h3 className="text-sm font-medium">只读 Diff</h3>
          <pre aria-label="只读 Diff" className="mt-2 max-h-96 overflow-auto rounded-md border bg-muted/30 p-3 font-mono text-xs leading-5">
            {proposal.diff || '没有可展示的 Diff。'}
          </pre>
        </section>
        {proposal.status === 'pending_confirmation' ? (
          <Button onClick={() => setConfirmationOpen(true)} disabled={confirming}>
            <CheckCircle2 className="size-4" />
            确认并快进目标分支
          </Button>
        ) : null}
      </CardContent>
      <Dialog open={confirmationOpen} onOpenChange={setConfirmationOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认应用检查点？</DialogTitle>
            <DialogDescription>
              后端会重新检查目标分支、基础 SHA 和干净工作区。若目标已变化，将返回 409 并保留可刷新的失败证据。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmationOpen(false)} disabled={confirming}>
              取消
            </Button>
            <Button
              onClick={() => {
                setConfirmationOpen(false)
                onConfirm()
              }}
              disabled={confirming}
            >
              {confirming ? '正在确认…' : '确认应用'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}
