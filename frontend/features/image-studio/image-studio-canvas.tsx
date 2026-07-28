'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Eraser, MousePointer2, Paintbrush } from 'lucide-react'

import { Button } from '@/components/ui/button'

import type { CanvasLayer, CanvasPoint, CanvasRecipe, CanvasStrokeLayer, MediaAsset } from './canvas-host-bridge'

type CanvasTool = 'select' | 'brush' | 'mask'

function drawStroke(context: CanvasRenderingContext2D, layer: CanvasStrokeLayer) {
  if (layer.points.length < 1) return
  context.save()
  context.globalAlpha = layer.opacity
  context.globalCompositeOperation = layer.blendMode
  context.strokeStyle = layer.tool === 'mask' ? 'rgba(255, 70, 150, .72)' : layer.color
  context.lineWidth = layer.size
  context.lineCap = 'round'
  context.lineJoin = 'round'
  context.beginPath()
  const first = layer.points[0]
  context.moveTo(first[0], first[1])
  for (const point of layer.points.slice(1)) context.lineTo(point[0], point[1])
  context.stroke()
  context.restore()
}

async function drawRecipe(canvas: HTMLCanvasElement, recipe: CanvasRecipe, assetUrls: ReadonlyMap<string, string>) {
  const context = canvas.getContext('2d')
  if (!context) return
  context.clearRect(0, 0, recipe.width, recipe.height)
  context.fillStyle = recipe.background
  context.fillRect(0, 0, recipe.width, recipe.height)

  for (const layer of recipe.layers) {
    if (!layer.visible) continue
    if (layer.type === 'stroke') {
      drawStroke(context, layer)
      continue
    }
    const contentUrl = assetUrls.get(layer.assetId)
    if (!contentUrl) continue
    const image = new Image()
    image.decoding = 'async'
    image.src = contentUrl
    try {
      await image.decode()
      context.save()
      context.globalAlpha = layer.opacity
      context.globalCompositeOperation = layer.blendMode
      context.drawImage(image, layer.x, layer.y, layer.width, layer.height)
      context.restore()
    } catch {
      // Missing previews remain non-destructive; the asset stays referenced in the document.
    }
  }
}

function pointerPoint(event: React.PointerEvent<HTMLCanvasElement>, recipe: CanvasRecipe): CanvasPoint {
  const bounds = event.currentTarget.getBoundingClientRect()
  return [
    ((event.clientX - bounds.left) / bounds.width) * recipe.width,
    ((event.clientY - bounds.top) / bounds.height) * recipe.height,
    event.pressure || 0.5,
  ]
}

export function ImageStudioCanvas({
  recipe,
  assets,
  onChange,
}: {
  recipe: CanvasRecipe
  assets: MediaAsset[]
  onChange: (recipe: CanvasRecipe) => void
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const drawingRef = useRef<CanvasStrokeLayer | null>(null)
  const [tool, setTool] = useState<CanvasTool>('brush')
  const assetUrls = useMemo(() => new Map(assets.map((asset) => [asset.id, asset.contentUrl])), [assets])

  useEffect(() => {
    const canvas = canvasRef.current
    if (canvas) void drawRecipe(canvas, recipe, assetUrls)
  }, [recipe, assetUrls])

  const commitStroke = useCallback((layer: CanvasLayer) => {
    onChange({ ...recipe, layers: [...recipe.layers, layer] })
  }, [onChange, recipe])

  const onPointerDown = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (tool === 'select') return
    event.currentTarget.setPointerCapture(event.pointerId)
    drawingRef.current = {
      id: globalThis.crypto?.randomUUID?.() ?? `stroke-${Date.now()}`,
      type: 'stroke',
      name: tool === 'mask' ? '蒙版' : '画笔',
      visible: true,
      opacity: 1,
      blendMode: 'source-over',
      tool,
      color: '#111111',
      size: tool === 'mask' ? 42 : 18,
      points: [pointerPoint(event, recipe)],
    }
  }

  const onPointerMove = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const layer = drawingRef.current
    if (!layer || !event.currentTarget.hasPointerCapture(event.pointerId)) return
    const next = { ...layer, points: [...layer.points, pointerPoint(event, recipe)] }
    drawingRef.current = next
    const canvas = canvasRef.current
    if (canvas) {
      void drawRecipe(canvas, recipe, assetUrls).then(() => {
        const context = canvas.getContext('2d')
        if (context) drawStroke(context, next)
      })
    }
  }

  const onPointerUp = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const layer = drawingRef.current
    drawingRef.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (layer && layer.points.length > 1) commitStroke(layer)
  }

  return (
    <div className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-[#111214] p-6">
      <div className="absolute left-4 top-4 z-10 flex gap-1 rounded-lg border border-white/10 bg-black/70 p-1 backdrop-blur">
        <Button aria-label="选择工具" variant={tool === 'select' ? 'secondary' : 'ghost'} size="icon" onClick={() => setTool('select')}>
          <MousePointer2 />
        </Button>
        <Button aria-label="画笔工具" variant={tool === 'brush' ? 'secondary' : 'ghost'} size="icon" onClick={() => setTool('brush')}>
          <Paintbrush />
        </Button>
        <Button aria-label="蒙版工具" variant={tool === 'mask' ? 'secondary' : 'ghost'} size="icon" onClick={() => setTool('mask')}>
          <Eraser />
        </Button>
      </div>
      <canvas
        ref={canvasRef}
        width={recipe.width}
        height={recipe.height}
        aria-label="图像创作画布"
        className="max-h-full max-w-full touch-none border border-white/10 bg-white shadow-2xl"
        style={{ aspectRatio: `${recipe.width} / ${recipe.height}` }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      />
    </div>
  )
}
