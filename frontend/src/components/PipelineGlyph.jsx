import { useEffect, useRef, useState } from 'react'

import { STAGE_LABELS } from './stages'

// The pipeline as a glyph picture: a hub with a spoke to each stage, rasterised to a
// grid of brightness levels and printed in characters from the stage keys. It turns
// slowly, flares to the accent under the pointer, and resolves from noise once on load.
const TEXT = STAGE_LABELS.map(([key]) => key.replace(/_/g, '')).join('')
const COLS = 96
const CELL_RATIO = 1.85
const TURN_MS = 60000
const INTRO_MS = 1500
const FLARE_PX = 56
const HEAT_HALF_LIFE_MS = 180
const LABEL_PX = 12

function readTokens() {
  const cs = getComputedStyle(document.documentElement)
  const v = (name) => cs.getPropertyValue(name).trim()
  return {
    glyph: Array.from({ length: 8 }, (_, i) => v(`--glyph-${i}`)),
    accent: v('--color-accent'),
    label: v('--color-ink-2'),
    font: v('--font-body'),
  }
}

export function PipelineGlyph() {
  const stageRef = useRef(null)
  const canvasRef = useRef(null)
  const pausedRef = useRef(false)
  const [paused, setPaused] = useState(false)

  useEffect(() => {
    pausedRef.current = paused
  }, [paused])

  useEffect(() => {
    const stage = stageRef.current
    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    const off = document.createElement('canvas')
    const octx = off.getContext('2d', { willReadFrequently: true })
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const tok = readTokens()
    const pointer = { x: 0, y: 0, on: false }
    const state = { hover: false, focus: false, seen: true }

    let W = 0
    let H = 0
    let cw = 1
    let ch = 1
    let rows = 0
    let heat = new Float32Array(0)
    let angle = 0
    let last = performance.now()
    let start = last
    let dirty = true
    let raf = 0

    function resize() {
      const dpr = window.devicePixelRatio || 1
      W = stage.clientWidth
      H = stage.clientHeight
      if (!W || !H) {
        rows = 0
        return
      }
      canvas.width = Math.round(W * dpr)
      canvas.height = Math.round(H * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      cw = W / COLS
      ch = cw * CELL_RATIO
      rows = Math.max(1, Math.floor(H / ch))
      off.width = COLS
      off.height = rows
      heat = new Float32Array(COLS * rows)
      dirty = true
    }

    function layout() {
      ctx.font = `500 ${LABEL_PX}px ${tok.font}`
      const sized = STAGE_LABELS.map(([, label]) => ({
        label,
        w: ctx.measureText(label).width + 28,
        h: 30,
      }))
      const maxW = Math.max(...sized.map((b) => b.w))
      const cx = W / 2
      const cy = (rows * ch) / 2
      const r = Math.max(40, Math.min(W / 2 - maxW / 2 - 8, cy - 23))
      const boxes = sized.map((b, i) => {
        const a = angle + (i * 2 * Math.PI) / sized.length - Math.PI / 2
        const x = cx + r * Math.cos(a)
        const y = cy + r * Math.sin(a)
        return { ...b, x: x - b.w / 2, y: y - b.h / 2, mx: x, my: y }
      })
      return { cx, cy, boxes }
    }

    function raster({ cx, cy, boxes }) {
      octx.setTransform(1, 0, 0, 1, 0, 0)
      octx.clearRect(0, 0, COLS, rows)
      octx.setTransform(1 / cw, 0, 0, 1 / ch, 0, 0)
      octx.strokeStyle = tok.label
      octx.fillStyle = tok.label
      const spokes = (width, alpha) => {
        octx.globalAlpha = alpha
        octx.lineWidth = width
        octx.beginPath()
        for (const b of boxes) {
          octx.moveTo(cx, cy)
          octx.lineTo(b.mx, b.my)
        }
        octx.stroke()
      }
      const hub = (radius, alpha) => {
        octx.globalAlpha = alpha
        octx.beginPath()
        octx.arc(cx, cy, radius, 0, Math.PI * 2)
        octx.fill()
      }
      spokes(24, 0.12)
      spokes(10, 0.3)
      spokes(4, 1)
      hub(48, 0.14)
      hub(26, 0.35)
      hub(12, 1)
      for (const b of boxes) {
        octx.clearRect(b.x - 6, b.y - 6, b.w + 12, b.h + 12)
        octx.globalAlpha = 0.25
        octx.lineWidth = 10
        octx.strokeRect(b.x, b.y, b.w, b.h)
        octx.globalAlpha = 1
        octx.lineWidth = 3
        octx.strokeRect(b.x, b.y, b.w, b.h)
      }
      octx.globalAlpha = 1
      return octx.getImageData(0, 0, COLS, rows).data
    }

    function inside(b, x, y, pad = 0) {
      return x > b.x + pad && x < b.x + b.w - pad && y > b.y + pad && y < b.y + b.h - pad
    }

    function draw(now) {
      const scene = layout()
      const data = raster(scene)
      const full = ch * 0.95
      const small = full * 0.62
      const reveal = reduce ? rows : ((now - start) / INTRO_MS) * rows
      const buckets = new Map()
      const put = (size, color, x, y, c) => {
        const key = `${size}|${color}`
        if (!buckets.has(key)) buckets.set(key, [])
        buckets.get(key).push(x, y, c)
      }

      for (let r = 0; r < rows; r += 1) {
        const y = (r + 0.5) * ch
        for (let c = 0; c < COLS; c += 1) {
          const k = r * COLS + c
          const x = (c + 0.5) * cw
          if (scene.boxes.some((b) => inside(b, x, y, 3))) continue
          const a = data[k * 4 + 3] / 255
          const level = a > 0.03 ? Math.min(8, Math.ceil(Math.pow(a, 0.7) * 8)) : 0
          const h = heat[k]
          if (r > reveal) {
            if (level) {
              const noise = TEXT[(Math.random() * TEXT.length) | 0]
              put(small, tok.glyph[(Math.random() * 3) | 0], x, y, noise)
            }
            continue
          }
          const ch0 = TEXT[k % TEXT.length]
          if (!level) {
            if (h > 0.2) put(small, tok.glyph[Math.round(h * 4)], x, y, ch0)
            continue
          }
          if (h > 0.55) {
            put(full, tok.accent, x, y, ch0)
            continue
          }
          const idx = Math.min(7, level - 1 + Math.round(h * 4))
          put(level <= 3 ? small : full, tok.glyph[idx], x, y, ch0)
        }
      }

      ctx.clearRect(0, 0, W, H)
      ctx.textAlign = 'center'
      ctx.textBaseline = 'middle'
      if ('fontStretch' in ctx) ctx.fontStretch = 'semi-condensed'
      for (const [key, cells] of buckets) {
        const [size, color] = key.split('|')
        ctx.font = `400 ${size}px ${tok.font}`
        ctx.fillStyle = color
        for (let i = 0; i < cells.length; i += 3) ctx.fillText(cells[i + 2], cells[i], cells[i + 1])
      }
      if ('fontStretch' in ctx) ctx.fontStretch = 'normal'
      ctx.font = `500 ${LABEL_PX}px ${tok.font}`
      for (const b of scene.boxes) {
        const hot = pointer.on && !reduce && inside(b, pointer.x, pointer.y)
        ctx.fillStyle = hot ? tok.accent : tok.label
        ctx.fillText(b.label, b.mx, b.my + 1)
      }
    }

    function frame(now) {
      raf = 0
      const dt = Math.min(64, now - last)
      last = now
      const spinning = !reduce && !pausedRef.current && !state.hover && !state.focus
      if (spinning) angle += (dt / TURN_MS) * Math.PI * 2

      let hot = false
      if (!reduce) {
        const keep = Math.pow(0.5, dt / HEAT_HALF_LIFE_MS)
        for (let i = 0; i < heat.length; i += 1) {
          if (heat[i] > 0.01) {
            heat[i] *= keep
            hot = true
          } else heat[i] = 0
        }
        if (pointer.on) {
          hot = true
          const c0 = Math.max(0, Math.floor((pointer.x - FLARE_PX) / cw))
          const c1 = Math.min(COLS - 1, Math.ceil((pointer.x + FLARE_PX) / cw))
          const r0 = Math.max(0, Math.floor((pointer.y - FLARE_PX) / ch))
          const r1 = Math.min(rows - 1, Math.ceil((pointer.y + FLARE_PX) / ch))
          for (let r = r0; r <= r1; r += 1) {
            for (let c = c0; c <= c1; c += 1) {
              const d = Math.hypot((c + 0.5) * cw - pointer.x, (r + 0.5) * ch - pointer.y)
              const k = r * COLS + c
              if (d < FLARE_PX) heat[k] = Math.max(heat[k], 1 - d / FLARE_PX)
            }
          }
        }
      }

      const intro = !reduce && now - start < INTRO_MS + 100
      if (rows && (spinning || hot || intro || dirty)) {
        dirty = false
        draw(now)
      }
      schedule()
    }

    function schedule() {
      if (!raf && state.seen && !document.hidden) raf = requestAnimationFrame(frame)
    }

    const onMove = (e) => {
      const rect = canvas.getBoundingClientRect()
      pointer.x = e.clientX - rect.left
      pointer.y = e.clientY - rect.top
      pointer.on = true
    }
    const onEnter = () => {
      state.hover = true
    }
    const onLeave = () => {
      state.hover = false
      pointer.on = false
    }
    const figure = stage.parentElement
    const onFocusIn = () => {
      state.focus = true
    }
    const onFocusOut = () => {
      state.focus = false
    }
    const onVisibility = () => {
      last = performance.now()
      schedule()
    }

    const ro = new ResizeObserver(() => {
      resize()
      schedule()
    })
    const io = new IntersectionObserver(([entry]) => {
      state.seen = entry.isIntersecting
      last = performance.now()
      schedule()
    })

    resize()
    ro.observe(stage)
    io.observe(stage)
    stage.addEventListener('pointermove', onMove)
    stage.addEventListener('pointerenter', onEnter)
    stage.addEventListener('pointerleave', onLeave)
    figure.addEventListener('focusin', onFocusIn)
    figure.addEventListener('focusout', onFocusOut)
    document.addEventListener('visibilitychange', onVisibility)
    document.fonts.ready.then(() => {
      start = performance.now()
      dirty = true
      schedule()
    })
    schedule()

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      io.disconnect()
      stage.removeEventListener('pointermove', onMove)
      stage.removeEventListener('pointerenter', onEnter)
      stage.removeEventListener('pointerleave', onLeave)
      figure.removeEventListener('focusin', onFocusIn)
      figure.removeEventListener('focusout', onFocusOut)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  return (
    <figure className="pipeline-diagram">
      <div className="pipeline-diagram__stage" ref={stageRef}>
        <canvas ref={canvasRef} aria-hidden="true" />
      </div>
      <button
        type="button"
        className="btn glyph-toggle"
        aria-pressed={paused}
        onClick={() => setPaused((current) => !current)}
      >
        {paused ? 'Play' : 'Pause'}
      </button>
    </figure>
  )
}
