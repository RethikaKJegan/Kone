import { useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentKey, ComponentPin, RepinTransform } from '../../types'

interface Props {
  imageUrl: string | null
  transform: RepinTransform
  label: string
  componentImageUrl?: string | null
  onChange: (transform: RepinTransform) => void
}

type DragMode = 'move' | 'resize-n' | 'resize-e' | 'resize-s' | 'resize-w' | 'resize-ne' | 'resize-se' | 'resize-sw' | 'resize-nw' | 'skew-x' | 'skew-y' | 'rotate'

const MIN_SIZE = 8

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function round(value: number) {
  return Math.round(value * 10) / 10
}

function defaultsFor(componentKey: ComponentKey) {
  if (componentKey === 'door') return { widthRatio: 0.34, heightRatio: 0.58 }
  if (componentKey === 'ceiling') return { widthRatio: 0.48, heightRatio: 0.22 }
  if (componentKey === 'cop') return { widthRatio: 0.12, heightRatio: 0.34 }
  return { widthRatio: 0.09, heightRatio: 0.22 }
}

export function repinTransformFromPin(
  componentKey: ComponentKey,
  sourceVersion: number,
  targetVersion: number,
  pin?: ComponentPin | null,
  imageSize: { width: number; height: number } = { width: 1000, height: 750 }
): RepinTransform {
  if (pin?.bbox && pin.bbox.length === 4) {
    const sourceWidth = pin.imageWidth || imageSize.width
    const sourceHeight = pin.imageHeight || imageSize.height
    const scaleX = imageSize.width / Math.max(1, sourceWidth)
    const scaleY = imageSize.height / Math.max(1, sourceHeight)
    const [x1, y1, x2, y2] = pin.bbox
    return {
      componentKey,
      componentType: componentKey,
      sourceVersion,
      targetVersion,
      x: round(clamp(x1 * scaleX, 0, Math.max(0, imageSize.width - MIN_SIZE))),
      y: round(clamp(y1 * scaleY, 0, Math.max(0, imageSize.height - MIN_SIZE))),
      width: round(clamp((x2 - x1) * scaleX, MIN_SIZE, imageSize.width)),
      height: round(clamp((y2 - y1) * scaleY, MIN_SIZE, imageSize.height)),
      rotation: 0,
      skewX: 0,
      skewY: 0,
      coordinateSpace: 'pixels',
      imageWidth: imageSize.width,
      imageHeight: imageSize.height,
      editableLayerUrl: pin.editableLayerUrl ?? null,
      repinBackgroundUrl: pin.repinBackgroundUrl ?? null,
      repinBackgroundDisplayUrl: pin.repinBackgroundDisplayUrl ?? pin.repinBackgroundUrl ?? null,
      feedbackOption: null,
    }
  }

  const defaults = defaultsFor(componentKey)
  const width = Math.max(MIN_SIZE, imageSize.width * defaults.widthRatio)
  const height = Math.max(MIN_SIZE, imageSize.height * defaults.heightRatio)
  const cx = ((pin?.x ?? 50) / 100) * imageSize.width
  const cy = ((pin?.y ?? 50) / 100) * imageSize.height
  return {
    componentKey,
    componentType: componentKey,
    sourceVersion,
    targetVersion,
    x: round(clamp(cx - width / 2, 0, Math.max(0, imageSize.width - MIN_SIZE))),
    y: round(clamp(cy - height / 2, 0, Math.max(0, imageSize.height - MIN_SIZE))),
    width: round(width),
    height: round(height),
    rotation: 0,
    skewX: 0,
    skewY: 0,
    coordinateSpace: 'pixels',
    imageWidth: imageSize.width,
    imageHeight: imageSize.height,
    editableLayerUrl: pin?.editableLayerUrl ?? null,
    repinBackgroundUrl: pin?.repinBackgroundUrl ?? null,
    repinBackgroundDisplayUrl: pin?.repinBackgroundDisplayUrl ?? pin?.repinBackgroundUrl ?? null,
    feedbackOption: null,
  }
}

export function RepinTransformCanvas({ imageUrl, transform, label, componentImageUrl, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const dragRef = useRef<{ mode: DragMode; startX: number; startY: number; start: RepinTransform } | null>(null)
  const [imageSize, setImageSize] = useState({ width: transform.imageWidth || 1000, height: transform.imageHeight || 750 })

  const normalized = useMemo(() => ({
    ...transform,
    coordinateSpace: 'pixels' as const,
    imageWidth: imageSize.width,
    imageHeight: imageSize.height,
  }), [transform, imageSize])

  const setTransform = (next: RepinTransform) => {
    const maxX = Math.max(0, imageSize.width - MIN_SIZE)
    const maxY = Math.max(0, imageSize.height - MIN_SIZE)
    const x = round(clamp(next.x, 0, maxX))
    const y = round(clamp(next.y, 0, maxY))
    const width = round(clamp(next.width, MIN_SIZE, imageSize.width - x))
    const height = round(clamp(next.height, MIN_SIZE, imageSize.height - y))
    onChange({
      ...next,
      x,
      y,
      width,
      height,
      rotation: round(next.rotation || 0),
      skewX: round(next.skewX),
      skewY: round(next.skewY),
      coordinateSpace: 'pixels',
      imageWidth: imageSize.width,
      imageHeight: imageSize.height,
    })
  }

  const pointFromEvent = (event: PointerEvent | React.PointerEvent) => {
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return null
    return {
      x: ((event.clientX - rect.left) / rect.width) * imageSize.width,
      y: ((event.clientY - rect.top) / rect.height) * imageSize.height,
    }
  }

  const beginDrag = (event: React.PointerEvent, mode: DragMode) => {
    const point = pointFromEvent(event)
    if (!point) return
    event.preventDefault()
    event.stopPropagation()
    dragRef.current = { mode, startX: point.x, startY: point.y, start: normalized }
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }

  useEffect(() => {
    const handleMove = (event: PointerEvent) => {
      const drag = dragRef.current
      const point = pointFromEvent(event)
      if (!drag || !point) return
      const dx = point.x - drag.startX
      const dy = point.y - drag.startY

      if (drag.mode === 'move') {
        setTransform({ ...drag.start, x: drag.start.x + dx, y: drag.start.y + dy })
        return
      }
      if (drag.mode === 'skew-x') {
        setTransform({ ...drag.start, skewX: drag.start.skewX + (dx / Math.max(1, imageSize.width)) * 180 })
        return
      }
      if (drag.mode === 'skew-y') {
        setTransform({ ...drag.start, skewY: drag.start.skewY + (dy / Math.max(1, imageSize.height)) * 180 })
        return
      }
      if (drag.mode === 'rotate') {
        const cx = drag.start.x + drag.start.width / 2
        const cy = drag.start.y + drag.start.height / 2
        const startAngle = Math.atan2(drag.startY - cy, drag.startX - cx)
        const nextAngle = Math.atan2(point.y - cy, point.x - cx)
        setTransform({ ...drag.start, rotation: (drag.start.rotation || 0) + ((nextAngle - startAngle) * 180) / Math.PI })
        return
      }

      let x = drag.start.x
      let y = drag.start.y
      let width = drag.start.width
      let height = drag.start.height
      if (drag.mode.includes('e')) width = Math.max(MIN_SIZE, drag.start.width + dx)
      if (drag.mode.includes('s')) height = Math.max(MIN_SIZE, drag.start.height + dy)
      if (drag.mode.includes('w')) {
        const right = drag.start.x + drag.start.width
        x = Math.min(right - MIN_SIZE, drag.start.x + dx)
        width = right - x
      }
      if (drag.mode.includes('n')) {
        const bottom = drag.start.y + drag.start.height
        y = Math.min(bottom - MIN_SIZE, drag.start.y + dy)
        height = bottom - y
      }
      setTransform({ ...drag.start, x, y, width, height })
    }

    const handleUp = () => {
      dragRef.current = null
    }

    window.addEventListener('pointermove', handleMove)
    window.addEventListener('pointerup', handleUp)
    return () => {
      window.removeEventListener('pointermove', handleMove)
      window.removeEventListener('pointerup', handleUp)
    }
  }, [normalized, imageSize])

  const boxStyle = useMemo(() => ({
    left: `${(normalized.x / imageSize.width) * 100}%`,
    top: `${(normalized.y / imageSize.height) * 100}%`,
    width: `${(normalized.width / imageSize.width) * 100}%`,
    height: `${(normalized.height / imageSize.height) * 100}%`,
    transform: `rotate(${normalized.rotation || 0}deg) skew(${normalized.skewX}deg, ${normalized.skewY}deg)`,
    transformOrigin: 'center center',
  }), [normalized, imageSize])

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-transparent" style={{ aspectRatio: `${imageSize.width} / ${imageSize.height}` }}>
      <div ref={containerRef} className="relative h-full w-full touch-none select-none">
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Generated preview"
            className="h-full w-full object-fill"
            onLoad={event => {
              const img = event.currentTarget
              const nextSize = { width: img.naturalWidth || imageSize.width, height: img.naturalHeight || imageSize.height }
              setImageSize(nextSize)
              if (transform.coordinateSpace !== 'pixels' || transform.imageWidth !== nextSize.width || transform.imageHeight !== nextSize.height) {
                const scaleX = nextSize.width / Math.max(1, transform.imageWidth || nextSize.width)
                const scaleY = nextSize.height / Math.max(1, transform.imageHeight || nextSize.height)
                onChange({
                  ...transform,
                  x: round(transform.x * scaleX),
                  y: round(transform.y * scaleY),
                  width: round(transform.width * scaleX),
                  height: round(transform.height * scaleY),
                  rotation: transform.rotation || 0,
                  coordinateSpace: 'pixels',
                  imageWidth: nextSize.width,
                  imageHeight: nextSize.height,
                })
              }
            }}
          />
        ) : <div className="h-full w-full bg-[#1A1A1A]" />}

        <div
          className="absolute overflow-visible border-2 border-[#1450F5] shadow-[0_0_0_1px_rgba(255,255,255,0.8)]"
          style={boxStyle}
          onPointerDown={event => beginDrag(event, 'move')}
          aria-label={`${label} transform box`}
        >
          {componentImageUrl ? <img src={componentImageUrl} alt={label} className="pointer-events-none absolute inset-0 h-full w-full object-fill" draggable={false} /> : null}
          <div className="pointer-events-none absolute left-1 top-1 rounded-[3px] bg-[#0A0A0A]/85 px-1.5 py-0.5 text-[10px] font-medium text-white">{label}</div>
          <button type="button" onPointerDown={event => beginDrag(event, 'rotate')} className="absolute left-1/2 top-[-34px] h-6 w-6 -translate-x-1/2 cursor-grab rounded-full border border-white bg-[#1450F5] text-[12px] font-semibold leading-none text-white shadow" aria-label="Rotate" title="Rotate">R</button>
          <button type="button" onPointerDown={event => beginDrag(event, 'skew-x')} className="absolute left-1/2 top-[-8px] h-4 w-8 -translate-x-1/2 cursor-ew-resize rounded-full border border-white bg-[#1450F5] text-[9px] font-semibold leading-none text-white shadow" aria-label="Skew X" title="Skew X">SX</button>
          <button type="button" onPointerDown={event => beginDrag(event, 'skew-y')} className="absolute right-[-8px] top-1/2 h-8 w-4 -translate-y-1/2 cursor-ns-resize rounded-full border border-white bg-[#1450F5] text-[8px] font-semibold leading-none text-white shadow" aria-label="Skew Y" title="Skew Y">SY</button>
          {[
            ['resize-nw', 'left-[-7px] top-[-7px] cursor-nwse-resize'],
            ['resize-n', 'left-1/2 top-[-7px] -translate-x-1/2 cursor-ns-resize'],
            ['resize-ne', 'right-[-7px] top-[-7px] cursor-nesw-resize'],
            ['resize-e', 'right-[-7px] top-1/2 -translate-y-1/2 cursor-ew-resize'],
            ['resize-se', 'bottom-[-7px] right-[-7px] cursor-nwse-resize'],
            ['resize-s', 'bottom-[-7px] left-1/2 -translate-x-1/2 cursor-ns-resize'],
            ['resize-sw', 'bottom-[-7px] left-[-7px] cursor-nesw-resize'],
            ['resize-w', 'left-[-7px] top-1/2 -translate-y-1/2 cursor-ew-resize'],
          ].map(([mode, className]) => (
            <button key={mode} type="button" onPointerDown={event => beginDrag(event, mode as DragMode)} className={`absolute rounded-full border border-white bg-[#1450F5] ${className}`} style={{ width: 14, height: 14 }} aria-label={mode} title="Resize / stretch" />
          ))}
        </div>
      </div>
    </div>
  )
}
