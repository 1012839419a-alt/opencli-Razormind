'use client'

import { useState, type FormEvent } from 'react'
import { Loader2, Pencil, Plus } from 'lucide-react'
import { toast } from 'sonner'

import { useCreatePlan, useUpdatePlan } from '@/lib/api/hooks'
import type { PlanGraph, PlanRead } from '@/lib/api/types'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// A brand-new Plan starts as an empty, structurally-valid graph — zero nodes
// trivially passes every check in backend.plan_ir.validation (duplicate ids,
// dangling edges, cycles, ... all vacuously true over an empty list). There
// is no node/edge authoring UI yet (that's the Collection Canvas; see
// endpoints.ts's "Plans (Plan IR issue 02)" comment — planCanvasModel.ts is
// referenced there but not built), so this dialog only collects a name and
// leaves graph authoring to that future canvas / the documented Plan IR API.
const EMPTY_GRAPH: PlanGraph = { ir_version: '1.0.0', draft: false, nodes: [], edges: [] }

export function PlanFormDialog({ plan }: { plan?: PlanRead }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(plan?.name ?? '')
  const createMutation = useCreatePlan()
  const updateMutation = useUpdatePlan()
  const pending = createMutation.isPending || updateMutation.isPending

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen)
    if (nextOpen) setName(plan?.name ?? '')
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const trimmed = name.trim()
    if (!trimmed) {
      toast.error('请填写计划名称')
      return
    }
    const options = {
      onSuccess: () => {
        toast.success(plan ? '计划已重命名' : '计划已创建')
        setOpen(false)
      },
      onError: (cause: Error) => toast.error(cause.message),
    }
    if (plan) updateMutation.mutate({ id: plan.id, data: { name: trimmed } }, options)
    else createMutation.mutate({ name: trimmed, graph: EMPTY_GRAPH }, options)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button size={plan ? 'xs' : 'sm'} variant={plan ? 'ghost' : 'default'} />}>
        {plan ? <Pencil className="size-3" /> : <Plus className="size-4" />}
        {plan ? '重命名' : '新建计划'}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit} className="flex flex-col gap-5">
          <DialogHeader>
            <DialogTitle>{plan ? '重命名计划' : '新建计划'}</DialogTitle>
            <DialogDescription>
              {plan
                ? '仅更新名称；节点与连线仍是上次保存的图，不受影响。'
                : '新计划从一张空图开始（0 个节点），保存后可通过 Plan IR API 继续编排；可视化画布编辑器尚未上线。'}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-2">
            <Label htmlFor="plan-name">计划名称</Label>
            <Input
              id="plan-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如：A股盘前情报采集"
              autoFocus
              required
            />
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? <Loader2 className="size-4 animate-spin" /> : null}
              {plan ? '保存' : '创建'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
