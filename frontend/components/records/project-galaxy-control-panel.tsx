'use client'

import { RotateCcw, X } from 'lucide-react'

import {
  DEFAULT_PROJECT_GALAXY_SETTINGS,
  type ProjectGalaxySettings,
} from '@/lib/records/project-galaxy-settings'
import { GALAXY_COLOR_THEMES } from '@/lib/records/project-galaxy-color-themes'

type ProjectGalaxyControlPanelProps = {
  settings: ProjectGalaxySettings
  onChange: (settings: ProjectGalaxySettings) => void
  onClose: () => void
  onRecenter: () => void
  onReset: () => void
}

export function ProjectGalaxyControlPanel({
  settings,
  onChange,
  onClose,
  onRecenter,
  onReset,
}: ProjectGalaxyControlPanelProps) {
  const patch = (value: Partial<ProjectGalaxySettings>) => onChange({ ...settings, ...value })

  return (
    <aside
      className="absolute right-3 top-3 z-30 max-h-[calc(100%-1.5rem)] overflow-y-auto rounded-lg border border-ops-line bg-ops-raised/95 text-zinc-200 shadow-overlay backdrop-blur-xl"
      style={{ width: settings.panelWidth }}
      aria-label="Galaxy 设置"
    >
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-ops-line bg-ops-raised/95 px-3 py-2.5">
        <div>
          <div className="text-sm font-semibold">Galaxy</div>
          <div className="text-3xs text-zinc-500">项目证据图设置</div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="grid size-8 place-items-center rounded-md text-zinc-400 hover:bg-muted hover:text-zinc-100"
          aria-label="关闭设置"
        >
          <X className="size-4" />
        </button>
      </header>

      <div className="space-y-2 p-3">
        <div className="grid grid-cols-2 gap-2">
          <PanelButton onClick={onRecenter}>重新居中</PanelButton>
          <PanelButton
            onClick={() => patch({ cruise: !settings.cruise })}
            active={settings.cruise}
          >
            自动环绕 {settings.cruise ? '●' : '○'}
          </PanelButton>
        </div>

        <PanelSection title="外观" defaultOpen>
          <RangeSetting
            label="节点大小"
            value={settings.look.nodeSize}
            min={0.3}
            max={2.5}
            step={0.05}
            format={(value) => `${value.toFixed(2)}×`}
            onChange={(nodeSize) => patch({ look: { ...settings.look, nodeSize } })}
          />
          <RangeSetting
            label="连线透明度"
            value={settings.look.linkOpacity}
            min={0}
            max={0.6}
            step={0.01}
            onChange={(linkOpacity) => patch({ look: { ...settings.look, linkOpacity } })}
          />
          <RangeSetting
            label="连线弯曲"
            value={settings.look.linkCurve}
            min={0}
            max={1}
            step={0.05}
            onChange={(linkCurve) => patch({ look: { ...settings.look, linkCurve } })}
          />
          <RangeSetting
            label="亮星眨眼"
            value={settings.look.twinkle}
            min={0}
            max={2}
            step={0.1}
            onChange={(twinkle) => patch({ look: { ...settings.look, twinkle } })}
          />
          <Segmented
            label="节点质量"
            value={settings.look.sizeBy}
            options={[
              { value: 'degree', label: '连接数' },
              { value: 'fileSize', label: '记录量' },
              { value: 'uniform', label: '统一' },
            ]}
            onChange={(sizeBy) => patch({
              look: { ...settings.look, sizeBy: sizeBy as ProjectGalaxySettings['look']['sizeBy'] },
            })}
          />
          <label className="block">
            <span className="mb-1.5 block text-2xs text-zinc-400">配色主题</span>
            <select
              value={settings.colorTheme}
              onChange={(event) => patch({ colorTheme: event.target.value })}
              className="min-h-9 w-full rounded-md border border-ops-line bg-ops-black/70 px-2 text-xs text-zinc-300"
            >
              {GALAXY_COLOR_THEMES.map((theme) => (
                <option key={theme.id} value={theme.id}>{theme.name}</option>
              ))}
            </select>
          </label>
        </PanelSection>

        <PanelSection title="光效" defaultOpen>
          <RangeSetting
            label="光晕强度"
            value={settings.bloom.strength}
            min={0}
            max={2}
            step={0.05}
            onChange={(strength) => patch({
              bloom: { ...settings.bloom, strength },
            })}
          />
          <RangeSetting
            label="光晕扩散"
            value={settings.bloom.radius}
            min={0}
            max={1}
            step={0.05}
            onChange={(radius) => patch({
              bloom: { ...settings.bloom, radius },
            })}
          />
          <RangeSetting
            label="发光阈值"
            value={settings.bloom.threshold}
            min={0}
            max={1}
            step={0.01}
            onChange={(threshold) => patch({
              bloom: { ...settings.bloom, threshold },
            })}
          />
          <p className="text-3xs leading-4 text-zinc-500">
            深空模式下启用；移动画质自动关闭以保证帧率。
          </p>
        </PanelSection>

        <PanelSection title="深空背景">
          <RangeSetting
            label="星云"
            value={settings.space.nebula}
            min={0}
            max={1}
            step={0.05}
            onChange={(nebula) => patch({ space: { ...settings.space, nebula } })}
          />
          <RangeSetting
            label="空间浮星"
            value={settings.space.fieldStars}
            min={0}
            max={1}
            step={0.05}
            onChange={(fieldStars) => patch({ space: { ...settings.space, fieldStars } })}
          />
          <RangeSetting
            label="集群云雾"
            value={settings.space.clusterClouds}
            min={0}
            max={1}
            step={0.05}
            onChange={(clusterClouds) => patch({
              space: { ...settings.space, clusterClouds },
            })}
          />
          <PanelButton
            onClick={() => patch({ showStarfield: !settings.showStarfield })}
            active={settings.showStarfield}
          >
            星空背景 {settings.showStarfield ? '开' : '关'}
          </PanelButton>
        </PanelSection>

        <PanelSection title="布局与物理">
          <RangeSetting
            label="排斥力"
            value={settings.physics.repel}
            min={20}
            max={500}
            step={5}
            onChange={(repel) => patch({ physics: { ...settings.physics, repel } })}
          />
          <RangeSetting
            label="链接距离"
            value={settings.physics.linkDistance}
            min={10}
            max={180}
            step={5}
            onChange={(linkDistance) => patch({
              physics: { ...settings.physics, linkDistance },
            })}
          />
          <RangeSetting
            label="链接强度"
            value={settings.physics.linkStrength}
            min={0.1}
            max={3}
            step={0.1}
            onChange={(linkStrength) => patch({
              physics: { ...settings.physics, linkStrength },
            })}
          />
          <RangeSetting
            label="中心引力"
            value={settings.physics.centerPull}
            min={0}
            max={0.3}
            step={0.01}
            onChange={(centerPull) => patch({ physics: { ...settings.physics, centerPull } })}
          />
          <RangeSetting
            label="星盘压扁"
            value={settings.physics.flatten}
            min={0}
            max={1}
            step={0.05}
            onChange={(flatten) => patch({ physics: { ...settings.physics, flatten } })}
          />
          <RangeSetting
            label="核心引力"
            value={settings.physics.coreGravity}
            min={-0.2}
            max={0.5}
            step={0.01}
            onChange={(coreGravity) => patch({
              physics: { ...settings.physics, coreGravity },
            })}
          />
          <RangeSetting
            label="旋臂"
            value={settings.physics.spiral}
            min={0}
            max={0.2}
            step={0.01}
            onChange={(spiral) => patch({ physics: { ...settings.physics, spiral } })}
          />
        </PanelSection>

        <PanelSection title="导航">
          <RangeSetting
            label="自动环绕速度"
            value={settings.cruiseSpeed}
            min={0.2}
            max={3}
            step={0.1}
            format={(value) => `${value.toFixed(1)}×`}
            onChange={(cruiseSpeed) => patch({ cruiseSpeed })}
          />
          <RangeSetting
            label="漫游速度"
            value={settings.tour.speed}
            min={0.2}
            max={3}
            step={0.1}
            format={(value) => `${value.toFixed(1)}×`}
            onChange={(speed) => patch({ tour: { speed } })}
          />
          <Segmented
            label="关联深度"
            value={String(settings.selectionDepth)}
            options={[
              { value: '1', label: '一度' },
              { value: '2', label: '二度' },
            ]}
            onChange={(value) => patch({ selectionDepth: value === '2' ? 2 : 1 })}
          />
        </PanelSection>

        <PanelSection title="高级">
          <Segmented
            label="质量"
            value={settings.qualityOverride}
            options={[
              { value: 'auto', label: '自动' },
              { value: 'high', label: '高' },
              { value: 'low', label: '低' },
              { value: 'mobile', label: '移动' },
            ]}
            onChange={(qualityOverride) => patch({
              qualityOverride: qualityOverride as ProjectGalaxySettings['qualityOverride'],
            })}
          />
          <Segmented
            label="主题"
            value={settings.preset}
            options={[
              { value: 'deep-space', label: '深空' },
              { value: 'adaptive', label: '自适应' },
            ]}
            onChange={(preset) => patch({
              preset: preset as ProjectGalaxySettings['preset'],
            })}
          />
          <PanelButton onClick={() => patch({ showOrphans: !settings.showOrphans })}>
            孤立节点 {settings.showOrphans ? '显示' : '隐藏'}
          </PanelButton>
        </PanelSection>

        <button
          type="button"
          onClick={onReset}
          className="flex min-h-9 w-full items-center justify-center gap-2 rounded-md border border-ops-line text-xs text-zinc-400 hover:bg-muted hover:text-zinc-100"
        >
          <RotateCcw className="size-3.5" />
          恢复全部默认值
        </button>

        <p className="px-1 text-3xs leading-4 text-zinc-600">
          默认参数来自 Galaxy View 0.6.0。项目数据适配为 OpenCLI 的来源、运行、记录与实体。
        </p>
      </div>
    </aside>
  )
}

function PanelSection({
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
      className="group rounded-md border border-ops-line bg-ops-panel"
      open={defaultOpen}
    >
      <summary className="cursor-pointer select-none px-3 py-2 text-xs font-medium text-zinc-300">
        {title}
      </summary>
      <div className="space-y-3 border-t border-ops-line p-3">{children}</div>
    </details>
  )
}

function RangeSetting({
  label,
  value,
  min,
  max,
  step,
  format = (candidate) => candidate.toFixed(2),
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  format?: (value: number) => string
  onChange: (value: number) => void
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex justify-between text-2xs text-zinc-400">
        <span>{label}</span>
        <span className="font-mono text-zinc-500">{format(value)}</span>
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

function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
}) {
  return (
    <div>
      <div className="mb-1.5 text-2xs text-zinc-400">{label}</div>
      <div className="flex flex-wrap rounded-md border border-ops-line bg-ops-black/70 p-1">
        {options.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => onChange(option.value)}
            className={`min-h-7 flex-1 rounded px-2 text-3xs ${
              value === option.value
                ? 'bg-muted text-zinc-100'
                : 'text-zinc-500 hover:text-zinc-200'
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  )
}

function PanelButton({
  children,
  onClick,
  active = false,
}: {
  children: React.ReactNode
  onClick: () => void
  active?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`min-h-9 w-full rounded-md border px-2 text-xs ${
        active
          ? 'border-violet-400/35 bg-violet-400/10 text-violet-200'
          : 'border-ops-line bg-ops-panel text-zinc-400 hover:bg-muted hover:text-zinc-100'
      }`}
    >
      {children}
    </button>
  )
}

export { DEFAULT_PROJECT_GALAXY_SETTINGS }
