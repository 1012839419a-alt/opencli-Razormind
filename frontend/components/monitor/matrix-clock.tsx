'use client'

import { useEffect, useState } from 'react'

import { cn } from '@/lib/utils'

const DIGITS = [
  ['111', '101', '101', '101', '111'],
  ['010', '110', '010', '010', '111'],
  ['111', '001', '111', '100', '111'],
  ['111', '001', '111', '001', '111'],
  ['101', '101', '111', '001', '001'],
  ['111', '100', '111', '001', '111'],
  ['111', '100', '111', '101', '111'],
  ['111', '001', '010', '010', '010'],
  ['111', '101', '111', '101', '111'],
  ['111', '101', '111', '001', '111'],
] as const

function PixelDigit({ value }: { value: number }) {
  return (
    <span className="grid grid-cols-3 gap-0.5" aria-hidden>
      {DIGITS[value].flatMap((row, rowIndex) =>
        [...row].map((pixel, columnIndex) => (
          <span
            key={`${rowIndex}-${columnIndex}`}
            className={cn(
              'size-[5px] rounded-full lg:size-1.5',
              pixel === '1'
                ? 'bg-white shadow-[0_0_6px_rgba(255,255,255,0.45)]'
                : 'bg-white/10',
            )}
          />
        )),
      )}
    </span>
  )
}

function Separator() {
  return (
    <span className="flex h-full flex-col justify-center gap-1.5" aria-hidden>
      <span className="size-1 rounded-full bg-white shadow-[0_0_5px_rgba(255,255,255,0.45)]" />
      <span className="size-1 rounded-full bg-white shadow-[0_0_5px_rgba(255,255,255,0.45)]" />
    </span>
  )
}

export function MatrixClock() {
  const [now, setNow] = useState<Date | null>(null)

  useEffect(() => {
    const update = () => setNow(new Date())
    update()
    const timer = window.setInterval(update, 1_000)
    return () => window.clearInterval(timer)
  }, [])

  const time = now?.toLocaleTimeString('zh-CN', { hour12: false }) ?? '--:--:--'
  const digits = now ? time.replaceAll(':', '').split('').map(Number) : []

  return (
    <div
      className="flex min-h-9 items-center gap-1.5 rounded-lg border border-white/10 bg-[#0c1110] px-2.5 py-1.5 shadow-sm"
      role="timer"
      aria-label={now ? `当前时间 ${time}` : '正在同步时间'}
      title={now ? `本地时间 ${time}` : '正在同步本地时间'}
    >
      {digits.length === 6 ? (
        digits.map((digit, index) => (
          <span key={index} className="contents">
            {index === 2 || index === 4 ? <Separator /> : null}
            <PixelDigit value={digit} />
          </span>
        ))
      ) : (
        <span className="font-mono text-[10px] tracking-[0.24em] text-white/60">SYNC</span>
      )}
    </div>
  )
}
