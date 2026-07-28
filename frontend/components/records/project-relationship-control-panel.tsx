'use client'

import { RotateCcw, X } from 'lucide-react'

export type ProjectRelationshipSettings = {
  showOrphans: boolean
  showLabels: boolean
  fadeUnrelated: boolean
  nodeSize: number
  linkThickness: number
  centerStrength: number
  repelStrength: number
  linkStrength: number
  linkDistance: number
}

export const DEFAULT_PROJECT_RELATIONSHIP_SETTINGS: ProjectRelationshipSettings = {
  showOrphans: true,
  showLabels: true,
  fadeUnrelated: true,
  nodeSize: 1,
  linkThickness: 1,
  centerStrength: 0.45,
  repelStrength: 48,
  linkStrength: 1,
  linkDistance: 38,
}

export function ProjectRelationshipControlPanel({
  settings,
  onChange,
  onClose,
  onRecenter,
}: {
  settings: ProjectRelationshipSettings
  onChange: (settings: ProjectRelationshipSettings) => void
  onClose: () => void
  onRecenter: () => void
}) {
  const patch = (value: Partial<ProjectRelationshipSettings>) => onChange({
    ...settings,
    ...value,
  })

  return (
    <aside className="absolute right-3 top-3 z-30 w-[19rem] overflow-hidden rounded-xl border border-white/10 bg-[#242424]/95 text-zinc-200 shadow-2xl backdrop-blur">
      <header className="flex items-center justify-between border-b border-white/10 px-3 py-2.5">
        <div>
          <div className="text-sm font-semibold">图谱控制</div>
          <div className="text-[10px] text-zinc-500">Obsidian Graph View 模式</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid size-8 place-items-center rounded-md text-zinc-400 hover:bg-white/10 hover:text-white"
          aria-label="关闭图谱控制"
        >
          <X className="size-4" />
        </button>
      </header>
      <div className="space-y-2 p-3">
        <RelationshipSection title="过滤" defaultOpen>
          <RelationshipToggle
            label="显示孤立节点"
            checked={settings.showOrphans}
            onChange={(showOrphans) => patch({ showOrphans })}
          />
        </RelationshipSection>
        <RelationshipSection title="显示" defaultOpen>
          <RelationshipToggle
            label="显示节点名称"
            checked={settings.showLabels}
            onChange={(showLabels) => patch({ showLabels })}
          />
          <RelationshipToggle
            label="淡化非邻接内容"
            checked={settings.fadeUnrelated}
            onChange={(fadeUnrelated) => patch({ fadeUnrelated })}
          />
          <RelationshipRange
            label="节点大小"
            value={settings.nodeSize}
            min={0.5}
            max={2}
            step={0.05}
            onChange={(nodeSize) => patch({ nodeSize })}
          />
          <RelationshipRange
            label="链接粗细"
            value={settings.linkThickness}
            min={0.3}
            max={2.5}
            step={0.05}
            onChange={(linkThickness) => patch({ linkThickness })}
          />
        </RelationshipSection>
        <RelationshipSection title="力" defaultOpen>
          <RelationshipRange
            label="中心力"
            value={settings.centerStrength}
            min={0}
            max={1}
            step={0.05}
            onChange={(centerStrength) => patch({ centerStrength })}
          />
          <RelationshipRange
            label="排斥力"
            value={settings.repelStrength}
            min={0}
            max={200}
            step={2}
            onChange={(repelStrength) => patch({ repelStrength })}
          />
          <RelationshipRange
            label="链接力"
            value={settings.linkStrength}
            min={0}
            max={2}
            step={0.05}
            onChange={(linkStrength) => patch({ linkStrength })}
          />
          <RelationshipRange
            label="链接距离"
            value={settings.linkDistance}
            min={10}
            max={150}
            step={2}
            onChange={(linkDistance) => patch({ linkDistance })}
          />
        </RelationshipSection>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            onClick={onRecenter}
            className="min-h-9 rounded-md border border-white/10 text-xs text-zinc-400 hover:bg-white/5 hover:text-white"
          >
            重新居中
          </button>
          <button
            type="button"
            onClick={() => onChange({ ...DEFAULT_PROJECT_RELATIONSHIP_SETTINGS })}
            className="flex min-h-9 items-center justify-center gap-1.5 rounded-md border border-white/10 text-xs text-zinc-400 hover:bg-white/5 hover:text-white"
          >
            <RotateCcw className="size-3.5" />
            恢复默认
          </button>
        </div>
      </div>
    </aside>
  )
}

function RelationshipSection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  return (
    <details
      open={defaultOpen}
      className="rounded-lg border border-white/10 bg-white/[0.02]"
    >
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium">
        {title}
      </summary>
      <div className="space-y-3 border-t border-white/10 p-3">{children}</div>
    </details>
  )
}

function RelationshipToggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-3 text-[11px] text-zinc-400">
      <span>{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="size-4 accent-violet-400"
      />
    </label>
  )
}

function RelationshipRange({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex justify-between text-[11px] text-zinc-400">
        <span>{label}</span>
        <span className="font-mono text-zinc-500">{value.toFixed(2)}</span>
      </span>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        className="h-1.5 w-full cursor-pointer accent-violet-400"
      />
    </label>
  )
}
