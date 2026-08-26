'use client'

import Image from 'next/image'
import { useEffect, useRef, useState } from 'react'

/*
 * Adapted from EldoraUI's MIT-style copy-paste component:
 * https://www.eldoraui.site/docs/components/testimonal-slider
 * The original uses Headless UI Transition and next/image; this version keeps
 * the same rotating avatar / quote / pill navigation interaction while using
 * the host app's image and transition primitives.
 */

export interface Testimonial {
  img?: string
  quote: string
  name: string
  role: string
}

export function FancyTestimonialsSlider({
  testimonials,
  autorotateTiming = 7000,
}: {
  testimonials: Testimonial[]
  autorotateTiming?: number
}) {
  const [active, setActive] = useState(0)
  const [autorotate, setAutorotate] = useState(true)
  const [hovered, setHovered] = useState(false)
  const sliderRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!autorotate || hovered || testimonials.length < 2) return
    const interval = window.setInterval(() => {
      setActive((current) => (current + 1) % testimonials.length)
    }, autorotateTiming)
    return () => window.clearInterval(interval)
  }, [autorotate, autorotateTiming, hovered, testimonials.length])

  if (!testimonials.length) return null

  function select(index: number) {
    setActive(index)
    setAutorotate(false)
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
    event.preventDefault()
    const delta = event.key === 'ArrowRight' ? 1 : -1
    select((active + delta + testimonials.length) % testimonials.length)
  }


  return (
    <div
      ref={sliderRef}
      tabIndex={0}
      onKeyDown={handleKeyDown}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      onFocus={() => setHovered(true)}
      onBlur={() => setHovered(false)}
      className="mx-auto w-full max-w-3xl px-4 text-center outline-none sm:px-6"
      aria-label="Agent 洞察轮播"
    >
      <div className="relative h-24 sm:h-28">
        <div className="pointer-events-none absolute top-0 left-1/2 h-[280px] w-[280px] -translate-x-1/2 before:absolute before:inset-0 before:-z-10 before:rounded-full before:bg-gradient-to-b before:from-cyan-500/25 before:via-cyan-500/5 before:via-25% before:to-cyan-500/0 before:to-75% sm:h-[360px] sm:w-[360px]">
          <div className="h-24 [mask-image:linear-gradient(0deg,transparent,white_20%,white)] sm:h-28">
            {testimonials.map((testimonial, index) => {
              const visible = active === index
              const initialsForItem = testimonial.name
                .split(/\s+/)
                .map((part) => part[0])
                .join('')
                .slice(0, 2)
                .toUpperCase()
              return (
                <div
                  key={`${testimonial.name}-${index}`}
                  className="absolute inset-0 h-full transition-[opacity,transform] duration-700"
                  style={{
                    opacity: visible ? 1 : 0,
                    transform: visible ? 'rotate(0deg)' : `rotate(${index < active ? '-60deg' : '60deg'})`,
                    pointerEvents: visible ? 'auto' : 'none',
                  }}
                  aria-hidden={!visible}
                >
                  {testimonial.img ? (
                    <Image className="relative top-8 left-1/2 size-12 -translate-x-1/2 rounded-full object-cover ring-4 ring-cyan-500/10 sm:top-10" src={testimonial.img} alt="" width={48} height={48} unoptimized />
                  ) : (
                    <span className="relative top-8 left-1/2 flex size-12 -translate-x-1/2 items-center justify-center rounded-full bg-gradient-to-br from-cyan-400 to-blue-600 text-sm font-semibold text-white ring-4 ring-cyan-500/10 sm:top-10" aria-hidden>
                      {initialsForItem}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="mb-6 min-h-[76px] transition-all delay-300 duration-150 ease-in-out sm:mb-8">
        <div className="relative flex flex-col">
          {testimonials.map((testimonial, index) => (
            <div
              key={`${testimonial.role}-${index}`}
              className="px-2 text-lg font-bold text-cyan-900 transition-[opacity,transform] duration-500 dark:text-cyan-100 sm:px-0 sm:text-xl"
              style={{
                opacity: active === index ? 1 : 0,
                transform: active === index ? 'translateX(0)' : `translateX(${index < active ? '-16px' : '16px'})`,
                position: active === index ? 'relative' : 'absolute',
                inset: active === index ? undefined : 0,
                pointerEvents: active === index ? 'auto' : 'none',
              }}
              aria-hidden={active !== index}
            >
              <span aria-hidden>“</span>
              {testimonial.quote}
              <span aria-hidden>”</span>
            </div>
          ))}
        </div>
      </div>

      <div className="-m-1 flex flex-wrap justify-center gap-1 sm:gap-1.5">
        {testimonials.map((testimonial, index) => (
          <button
            key={`${testimonial.name}-${testimonial.role}`}
            type="button"
            aria-pressed={active === index}
            aria-label={`查看 ${testimonial.name} 的洞察`}
            onClick={() => select(index)}
            className={`m-1 inline-flex max-w-full justify-center rounded-full px-2 py-1 text-xs whitespace-nowrap shadow-sm transition-colors duration-150 focus-visible:ring-2 focus-visible:ring-cyan-300 focus-visible:outline-none sm:px-3 sm:py-1.5 dark:focus-visible:ring-cyan-600 ${active === index ? 'bg-cyan-500 text-white shadow-cyan-950/10' : 'bg-white text-cyan-900 hover:bg-cyan-100 dark:bg-slate-800 dark:text-cyan-100 dark:hover:bg-slate-700'}`}
          >
            <span className="truncate">{testimonial.name}</span>
            <span className={active === index ? 'px-1 text-cyan-200' : 'px-1 text-cyan-300'} aria-hidden>-</span>
            <span className="truncate">{testimonial.role}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

export default FancyTestimonialsSlider
