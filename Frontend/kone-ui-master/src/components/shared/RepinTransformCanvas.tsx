import { useEffect, useMemo, useRef, useState } from 'react'
import { RotateCw } from 'lucide-react'
import type { ComponentKey, RepinTransform } from '../../types'

interface Props {
  imageUrl: string | null
  componentImageUrl?: string | null
  transform: RepinTransform
  label: string
  onChange: (transform: RepinTransform) => void
}

type DragMode = 'move' | 'resize-e' | 'resize-s' | 'resize-se' | 'rotate' | 'skew-x' | 'skew-y' | 'corner-0' | 'corner-1' | 'corner-2' | 'corner-3'

const MIN_SIZE = 4

function clamp(value: number, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value))
}

function round(value: number) {
  return Math.round(value * 10) / 10
}

function defaultPerspective(transform: RepinTransform) {
  return [
    { x: transform.x, y: transform.y },
    { x: transform.x + transform.width, y: transform.y },
    { x: transform.x + transform.width, y: transform.y + transform.height },
    { x: transform.x, y: transform.y + transform.height },
  ]
}

export function repinTransformFromPin(
  componentKey: ComponentKey,
  sourceVersion: number,
  targetVersion: number,
  pin?: { x: number; y: number } | null
): RepinTransform {
  const width = componentKey === 'door' ? 34 : componentKey === 'ceiling' ? 48 : componentKey === 'cop' ? 12 : 9
  const height = componentKey === 'door' ? 58 : componentKey === 'ceiling' ? 22 : componentKey === 'cop' ? 34 : 22
  const transform: RepinTransform = {
    componentKey,
    componentType: componentKey,
    sourceVersion,
    targetVersion,
    x: clamp((pin?.x ?? 50) - width / 2),
    y: clamp((pin?.y ?? 50) - height / 2),
    width,
    height,
    rotation: 0,
    skewX: 0,
    skewY: 0,
    perspective: [],
    feedbackOption: null,
  }
  transform.perspective = defaultPerspective(transform)
  return transform
}

export function RepinTransformCanvas({ imageUrl, componentImageUrl, transform, label, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ mode: DragMode; startX: number; startY: number; start: RepinTransform } | null>(null)
  const [, forceTick] = useState(0)
  const perspective = transform.perspective?.length === 4 ? transform.perspective : defaultPerspective(transform)

  const setTransform = (next: RepinTransform) => {
    onChange({
      ...next,
      x: round(clamp(next.x)),
      y: round(clamp(next.y)),
      width: round(clamp(next.width, MIN_SIZE)),
      height: round(clamp(next.height, MIN_SIZE)),
      rotation: round(next.rotation),
      skewX: round(next.skewX),
      skewY: round(next.skewY),
      perspective: (next.perspective?.length === 4 ? next.perspective : defaultPerspective(next)).map(point => ({
        x: round(clamp(point.x)),
        y: round(clamp(point.y)),
      })),
    })
  }

  const pointFromEvent = (event: PointerEvent | React.PointerEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return null
    return {
      x: ((event.clientX - rect.left) / rect.width) * 100,
      y: ((event.clientY - rect.top) / rect.height) * 100,
    }
  }

  const beginDrag = (event: React.PointerEvent, mode: DragMode) => {
    const point = pointFromEvent(event)
    if (!point) return
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = { mode, startX: point.x, startY: point.y, start: { ...transform, perspective } }
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }

  useEffect(() => {
    const handleMove = (event: PointerEvent) => {
      const drag = dragRef.current
      const point = pointFromEvent(event)
      if (!drag || !point) return
      const dx = point.x - drag.startX
      const dy = point.y - drag.startY
      const startPerspective = drag.start.perspective?.length === 4 ? drag.start.perspective : defaultPerspective(drag.start)

      if (drag.mode === 'move') {
        setTransform({
          ...drag.start,
          x: drag.start.x + dx,
          y: drag.start.y + dy,
          perspective: startPerspective.map(corner => ({ x: corner.x + dx, y: corner.y + dy })),
        })
        return
      }
      if (drag.mode === 'rotate') {
        const cx = drag.start.x + drag.start.width / 2
        const cy = drag.start.y + drag.start.height / 2
        setTransform({ ...drag.start, rotation: Math.atan2(point.y - cy, point.x - cx) * (180 / Math.PI) + 90 })
        return
      }
      if (drag.mode === 'skew-x') {
        setTransform({ ...drag.start, skewX: drag.start.skewX + dx * 2 })
        return
      }
      if (drag.mode === 'skew-y') {
        setTransform({ ...drag.start, skewY: drag.start.skewY + dy * 2 })
        return
      }
      const cornerMatch = drag.mode.match(/^corner-(\d)$/)
      if (cornerMatch) {
        const index = Number(cornerMatch[1])
        setTransform({
          ...drag.start,
          perspective: startPerspective.map((corner, cornerIndex) => cornerIndex === index ? { x: corner.x + dx, y: corner.y + dy } : corner),
        })
        return
      }
      const width = drag.mode.includes('e') ? Math.max(MIN_SIZE, drag.start.width + dx) : drag.start.width
      const height = drag.mode.includes('s') ? Math.max(MIN_SIZE, drag.start.height + dy) : drag.start.height
      const next = { ...drag.start, width, height }
      setTransform({ ...next, perspective: defaultPerspective(next) })
    }

    const handleUp = () => {
      dragRef.current = null
      forceTick(value => value + 1)
    }

    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
    return () => {
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
    }
  }, [transform])

  const boxStyle = useMemo(() => ({
    left: `${transform.x}%`,
    top: `${transform.y}%`,
    width: `${transform.width}%`,
    height: `${transform.height}%`,
    transform: `rotate(${transform.rotation}deg) skew(${transform.skewX}deg, ${transform.skewY}deg)`,
    transformOrigin: 'center center',
  }), [transform])

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-[#0A0A0A]" style={{ aspectRatio: '4/3' }}>
      <div ref={containerRef} className="relative h-full w-full touch-none select-none">
        {imageUrl ? <img src={imageUrl} alt="Generated preview" className="h-full w-full object-cover" /> : <div className="h-full w-full bg-[#1A1A1A]" />}

        <div
          className="absolute border-2 border-[#1450F5] bg-[#1450F5]/10 shadow-[0_0_0_1px_rgba(255,255,255,0.7)]"
          style={boxStyle}
          onPointerDown={event => beginDrag(event, 'move')}
          aria-label={`${label} transform box`}
        >
          {componentImageUrl && <img src={componentImageUrl} alt="" className="h-full w-full object-fill opacity-70" draggable={false} />}
          <div className="absolute left-1 top-1 rounded-[3px] bg-[#0A0A0A]/85 px-1.5 py-0.5 text-[10px] font-medium text-white">
            {label}
          </div>
          <button
            type="button"
            onPointerDown={event => beginDrag(event, 'rotate')}
            className="absolute left-1/2 top-[-34px] flex -translate-x-1/2 items-center justify-center rounded-full bg-white text-[#1450F5] shadow"
            style={{ width: 24, height: 24 }}
            aria-label="Rotate"
            title="Rotate"
          >
            <RotateCw style={{ width: 13, height: 13 }} />
          </button>
          <button
            type="button"
            onPointerDown={event => beginDrag(event, 'skew-x')}
            className="absolute left-1/2 top-[-8px] h-4 w-8 -translate-x-1/2 cursor-ew-resize rounded-full border border-white bg-[#1450F5] text-[9px] font-semibold leading-none text-white shadow"
            aria-label="Skew X"
            title="Skew X"
          >
            SX
          </button>
          <button
            type="button"
            onPointerDown={event => beginDrag(event, 'skew-y')}
            className="absolute right-[-8px] top-1/2 h-8 w-4 -translate-y-1/2 cursor-ns-resize rounded-full border border-white bg-[#1450F5] text-[8px] font-semibold leading-none text-white shadow"
            aria-label="Skew Y"
            title="Skew Y"
          >
            SY
          </button>
          {[
            ['resize-e', 'right-[-7px] top-1/2 -translate-y-1/2 cursor-ew-resize'],
            ['resize-s', 'bottom-[-7px] left-1/2 -translate-x-1/2 cursor-ns-resize'],
            ['resize-se', 'bottom-[-7px] right-[-7px] cursor-nwse-resize'],
          ].map(([mode, className]) => (
            <button
              key={mode}
              type="button"
              onPointerDown={event => beginDrag(event, mode as DragMode)}
              className={`absolute rounded-full border border-white bg-[#1450F5] ${className}`}
              style={{ width: 14, height: 14 }}
              aria-label={mode}
            />
          ))}
        </div>

        {perspective.map((point, index) => (
          <button
            key={index}
            type="button"
            onPointerDown={event => beginDrag(event, `corner-${index}` as DragMode)}
            className="absolute rounded-[3px] border-2 border-white bg-[#1450F5] shadow"
            style={{ left: `${point.x}%`, top: `${point.y}%`, width: 14, height: 14, transform: 'translate(-50%, -50%)' }}
            aria-label={`Perspective corner ${index + 1}`}
            title={`Perspective corner ${index + 1}`}
          />
        ))}
      </div>
    </div>
  )
}
