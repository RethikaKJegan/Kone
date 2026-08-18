import { useEffect, useMemo, useRef, useState } from 'react'
import type { ComponentKey, ComponentPin, RepinTransform } from '../../types'

interface Props {
  imageUrl: string | null
  transform: RepinTransform
  label: string
  componentImageUrl?: string | null
  staticLayers?: { transform: RepinTransform; label: string; componentImageUrl: string | null; onSelect?: () => void }[]
  eraserEnabled?: boolean
  eraserBrushSize?: number
  previewOnly?: boolean
  onErase?: (maskDataUrl: string) => void
  onEditStart?: (transform: RepinTransform) => void
  onChange: (transform: RepinTransform) => void
}

type QuadPoint = { x: number; y: number }
type QuadPoints = [QuadPoint, QuadPoint, QuadPoint, QuadPoint]
type DragMode = 'move' | 'corner-0' | 'corner-1' | 'corner-2' | 'corner-3' | 'edge-top' | 'edge-right' | 'edge-bottom' | 'edge-left' | 'rotate' | 'skew-x' | 'skew-y'

const MIN_SIZE = 8
const ERASER_CURSOR = `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='28' height='28' viewBox='0 0 28 28'%3E%3Cg fill='none' stroke='%231450F5' stroke-width='2' stroke-linejoin='round'%3E%3Cpath fill='white' d='M5 17 16 6l7 7-11 11H5z'/%3E%3Cpath d='m12 24 11-11'/%3E%3C/g%3E%3C/svg%3E") 5 22, crosshair`
const CORNERS = [
  { label: 'Top left', cursor: 'cursor-nwse-resize' },
  { label: 'Top right', cursor: 'cursor-nesw-resize' },
  { label: 'Bottom right', cursor: 'cursor-nwse-resize' },
  { label: 'Bottom left', cursor: 'cursor-nesw-resize' },
] as const

const EDGE_HANDLES = [
  { mode: "edge-top", label: "Top edge", cursor: "cursor-ns-resize" },
  { mode: "edge-right", label: "Right edge", cursor: "cursor-ew-resize" },
  { mode: "edge-bottom", label: "Bottom edge", cursor: "cursor-ns-resize" },
  { mode: "edge-left", label: "Left edge", cursor: "cursor-ew-resize" },
] as const

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value))
}

function round(value: number) {
  return Math.round(value * 10) / 10
}

function finiteNumber(value: unknown, fallback: number) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function validQuadPoints(value: unknown): value is QuadPoints {
  return Array.isArray(value) && value.length === 4 && value.every(point => (
    point &&
    typeof point === 'object' &&
    typeof (point as QuadPoint).x === 'number' &&
    Number.isFinite((point as QuadPoint).x) &&
    typeof (point as QuadPoint).y === 'number' &&
    Number.isFinite((point as QuadPoint).y)
  ))
}

function pointsFromRect(transform: Pick<RepinTransform, 'x' | 'y' | 'width' | 'height'>): QuadPoints {
  const x = finiteNumber(transform.x, 0)
  const y = finiteNumber(transform.y, 0)
  const width = Math.max(MIN_SIZE, finiteNumber(transform.width, MIN_SIZE))
  const height = Math.max(MIN_SIZE, finiteNumber(transform.height, MIN_SIZE))
  return [
    { x, y },
    { x: x + width, y },
    { x: x + width, y: y + height },
    { x, y: y + height },
  ]
}

function boundingBoxFromPoints(points: QuadPoints, imageSize: { width: number; height: number }) {
  const xs = points.map(point => point.x)
  const ys = points.map(point => point.y)
  const x1 = clamp(Math.min(...xs), 0, Math.max(0, imageSize.width - MIN_SIZE))
  const y1 = clamp(Math.min(...ys), 0, Math.max(0, imageSize.height - MIN_SIZE))
  const x2 = clamp(Math.max(...xs), x1 + MIN_SIZE, imageSize.width)
  const y2 = clamp(Math.max(...ys), y1 + MIN_SIZE, imageSize.height)
  return { x: round(x1), y: round(y1), width: round(x2 - x1), height: round(y2 - y1) }
}

function clampPoints(points: QuadPoints, imageSize: { width: number; height: number }): QuadPoints {
  return points.map(point => ({
    x: round(clamp(point.x, 0, imageSize.width)),
    y: round(clamp(point.y, 0, imageSize.height)),
  })) as QuadPoints
}


function midpoint(a: QuadPoint, b: QuadPoint): QuadPoint {
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}

function quadCenter(points: QuadPoints): QuadPoint {
  return points.reduce((acc, point) => ({ x: acc.x + point.x / 4, y: acc.y + point.y / 4 }), { x: 0, y: 0 })
}

function rotatePoints(points: QuadPoints, center: QuadPoint, radians: number): QuadPoints {
  const cos = Math.cos(radians)
  const sin = Math.sin(radians)
  return points.map(point => {
    const x = point.x - center.x
    const y = point.y - center.y
    return {
      x: center.x + x * cos - y * sin,
      y: center.y + x * sin + y * cos,
    }
  }) as QuadPoints
}

function scalePointsFromAnchor(points: QuadPoints, anchorIndex: number, dragIndex: number, target: QuadPoint): QuadPoints {
  const anchor = points[anchorIndex]
  const startDrag = points[dragIndex]
  const startDistance = Math.hypot(startDrag.x - anchor.x, startDrag.y - anchor.y)
  if (startDistance < MIN_SIZE) return points
  const nextDistance = Math.hypot(target.x - anchor.x, target.y - anchor.y)
  const scale = Math.max(MIN_SIZE / startDistance, nextDistance / startDistance)
  return points.map(point => ({
    x: anchor.x + (point.x - anchor.x) * scale,
    y: anchor.y + (point.y - anchor.y) * scale,
  })) as QuadPoints
}

function moveEdge(points: QuadPoints, mode: DragMode, dx: number, dy: number, imageSize: { width: number; height: number }): QuadPoints {
  const next = points.map(point => ({ ...point })) as QuadPoints
  if (mode === 'edge-top') {
    const minDy = -Math.min(points[0].y, points[1].y)
    const maxDy = Math.min(points[2].y - points[0].y - MIN_SIZE, points[3].y - points[1].y - MIN_SIZE)
    const edgeDy = clamp(dy, minDy, maxDy)
    next[0].y = points[0].y + edgeDy
    next[1].y = points[1].y + edgeDy
  } else if (mode === 'edge-bottom') {
    const minDy = Math.max(points[0].y - points[2].y + MIN_SIZE, points[1].y - points[3].y + MIN_SIZE)
    const maxDy = imageSize.height - Math.max(points[2].y, points[3].y)
    const edgeDy = clamp(dy, minDy, maxDy)
    next[2].y = points[2].y + edgeDy
    next[3].y = points[3].y + edgeDy
  } else if (mode === 'edge-left') {
    const minDx = -Math.min(points[0].x, points[3].x)
    const maxDx = Math.min(points[1].x - points[0].x - MIN_SIZE, points[2].x - points[3].x - MIN_SIZE)
    const edgeDx = clamp(dx, minDx, maxDx)
    next[0].x = points[0].x + edgeDx
    next[3].x = points[3].x + edgeDx
  } else if (mode === 'edge-right') {
    const minDx = Math.max(points[0].x - points[1].x + MIN_SIZE, points[3].x - points[2].x + MIN_SIZE)
    const maxDx = imageSize.width - Math.max(points[1].x, points[2].x)
    const edgeDx = clamp(dx, minDx, maxDx)
    next[1].x = points[1].x + edgeDx
    next[2].x = points[2].x + edgeDx
  }
  return next
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
  if (pin?.bbox && pin.bbox.length === 4 && pin.imageWidth && pin.imageHeight) {
    const sourceWidth = pin.imageWidth
    const sourceHeight = pin.imageHeight
    const [x1, y1, x2, y2] = pin.bbox
    const base = {
      componentKey,
      componentType: componentKey,
      sourceVersion,
      targetVersion,
      x: round(clamp(x1, 0, Math.max(0, sourceWidth - MIN_SIZE))),
      y: round(clamp(y1, 0, Math.max(0, sourceHeight - MIN_SIZE))),
      width: round(clamp(x2 - x1, MIN_SIZE, sourceWidth)),
      height: round(clamp(y2 - y1, MIN_SIZE, sourceHeight)),
      rotation: 0,
      skewX: 0,
      skewY: 0,
      coordinateSpace: 'pixels' as const,
      imageWidth: sourceWidth,
      imageHeight: sourceHeight,
      originalBbox: pin.bbox,
      originalImageWidth: sourceWidth,
      originalImageHeight: sourceHeight,
      editableLayerUrl: pin.editableLayerUrl ?? null,
      repinBackgroundUrl: pin.repinBackgroundUrl ?? null,
      repinBackgroundDisplayUrl: pin.repinBackgroundDisplayUrl ?? pin.repinBackgroundUrl ?? null,
      feedbackOption: null,
    }
    return { ...base, points: pointsFromRect(base) }
  }

  const defaults = defaultsFor(componentKey)
  const width = Math.max(MIN_SIZE, imageSize.width * defaults.widthRatio)
  const height = Math.max(MIN_SIZE, imageSize.height * defaults.heightRatio)
  const cx = ((pin?.x ?? 50) / 100) * imageSize.width
  const cy = ((pin?.y ?? 50) / 100) * imageSize.height
  const base = {
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
    coordinateSpace: 'pixels' as const,
    imageWidth: imageSize.width,
    imageHeight: imageSize.height,
    originalBbox: pin?.bbox ?? null,
    originalImageWidth: pin?.imageWidth ?? null,
    originalImageHeight: pin?.imageHeight ?? null,
    editableLayerUrl: pin?.editableLayerUrl ?? null,
    repinBackgroundUrl: pin?.repinBackgroundUrl ?? null,
    repinBackgroundDisplayUrl: pin?.repinBackgroundDisplayUrl ?? pin?.repinBackgroundUrl ?? null,
    feedbackOption: null,
  }
  return { ...base, points: pointsFromRect(base) }
}

function layerBox(transform: RepinTransform, imageSize: { width: number; height: number }) {
  const scaleX = imageSize.width / Math.max(1, transform.imageWidth || imageSize.width)
  const scaleY = imageSize.height / Math.max(1, transform.imageHeight || imageSize.height)
  const points = validQuadPoints(transform.points)
    ? transform.points.map(point => ({ x: round(point.x * scaleX), y: round(point.y * scaleY) })) as QuadPoints
    : pointsFromRect({
      x: round(transform.x * scaleX),
      y: round(transform.y * scaleY),
      width: round(transform.width * scaleX),
      height: round(transform.height * scaleY),
    })
  const clampedPoints = clampPoints(points, imageSize)
  const bbox = boundingBoxFromPoints(clampedPoints, imageSize)
  const relativePolygon = clampedPoints.map(point => {
    const x = bbox.width > 0 ? ((point.x - bbox.x) / bbox.width) * 100 : 0
    const y = bbox.height > 0 ? ((point.y - bbox.y) / bbox.height) * 100 : 0
    return String(round(x)) + '% ' + String(round(y)) + '%'
  }).join(', ')
  return { bbox, relativePolygon }
}

export function RepinTransformCanvas({ imageUrl, transform, label, componentImageUrl, staticLayers = [], eraserEnabled = false, eraserBrushSize = 32, previewOnly = false, onErase, onEditStart, onChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const eraserCanvasRef = useRef<HTMLCanvasElement>(null)
  const eraserDrawingRef = useRef(false)
  const lastEraserPointRef = useRef<QuadPoint | null>(null)
  const dragRef = useRef<{ mode: DragMode; startX: number; startY: number; start: RepinTransform } | null>(null)
  const [imageSize, setImageSize] = useState({ width: transform.imageWidth || 1000, height: transform.imageHeight || 750 })

  const normalized = useMemo(() => {
    const fallback = repinTransformFromPin(transform.componentKey, transform.sourceVersion, transform.targetVersion, null, imageSize)
    const rawX = finiteNumber(transform.x, fallback.x)
    const rawY = finiteNumber(transform.y, fallback.y)
    const rawWidth = finiteNumber(transform.width, fallback.width)
    const rawHeight = finiteNumber(transform.height, fallback.height)
    const isUsable =
      rawWidth >= MIN_SIZE &&
      rawHeight >= MIN_SIZE &&
      rawX >= 0 &&
      rawY >= 0 &&
      rawX <= imageSize.width - MIN_SIZE &&
      rawY <= imageSize.height - MIN_SIZE
    const base = isUsable ? transform : fallback
    const x = round(clamp(finiteNumber(base.x, fallback.x), 0, Math.max(0, imageSize.width - MIN_SIZE)))
    const y = round(clamp(finiteNumber(base.y, fallback.y), 0, Math.max(0, imageSize.height - MIN_SIZE)))
    const rectBase = {
      x,
      y,
      width: round(clamp(finiteNumber(base.width, fallback.width), MIN_SIZE, imageSize.width - x)),
      height: round(clamp(finiteNumber(base.height, fallback.height), MIN_SIZE, imageSize.height - y)),
    }
    const points = clampPoints(validQuadPoints(base.points) ? base.points : pointsFromRect(rectBase), imageSize)
    const bbox = boundingBoxFromPoints(points, imageSize)
    return {
      ...base,
      ...bbox,
      points,
      rotation: finiteNumber(base.rotation, 0),
      skewX: finiteNumber(base.skewX, 0),
      skewY: finiteNumber(base.skewY, 0),
      coordinateSpace: 'pixels' as const,
      imageWidth: imageSize.width,
      imageHeight: imageSize.height,
    }
  }, [transform, imageSize])

  const setTransform = (next: RepinTransform) => {
    const points = clampPoints(validQuadPoints(next.points) ? next.points : pointsFromRect(next), imageSize)
    const bbox = boundingBoxFromPoints(points, imageSize)
    onChange({
      ...next,
      ...bbox,
      points,
      rotation: round(finiteNumber(next.rotation, 0)),
      skewX: round(finiteNumber(next.skewX, 0)),
      skewY: round(finiteNumber(next.skewY, 0)),
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


  const rememberAssetAspectRatio = (naturalWidth: number, naturalHeight: number) => {
    if (!naturalWidth || !naturalHeight || normalized.assetAspectRatio) return
    const aspectRatio = naturalWidth / naturalHeight
    if (!Number.isFinite(aspectRatio) || aspectRatio <= 0) return

    setTransform({ ...normalized, assetAspectRatio: aspectRatio })
  }

  const prepareEraserCanvas = () => {
    const canvas = eraserCanvasRef.current
    if (!canvas) return null
    if (canvas.width !== imageSize.width || canvas.height !== imageSize.height) {
      canvas.width = imageSize.width
      canvas.height = imageSize.height
    }
    return canvas
  }

  useEffect(() => {
    const canvas = prepareEraserCanvas()
    const ctx = canvas?.getContext('2d')
    if (ctx) ctx.clearRect(0, 0, canvas!.width, canvas!.height)
    eraserDrawingRef.current = false
    lastEraserPointRef.current = null
  }, [eraserEnabled, imageSize])

  const drawEraserStroke = (from: QuadPoint, to: QuadPoint) => {
    const canvas = prepareEraserCanvas()
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return
    ctx.save()
    ctx.strokeStyle = 'rgba(20,80,245,0.82)'
    ctx.lineWidth = eraserBrushSize
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.beginPath()
    ctx.moveTo(from.x, from.y)
    ctx.lineTo(to.x, to.y)
    ctx.stroke()
    ctx.restore()
  }


  const compactMaskDataUrl = (canvas: HTMLCanvasElement) => {
    const maxSide = 1400
    const scale = Math.min(1, maxSide / Math.max(canvas.width, canvas.height))
    if (scale >= 1) return canvas.toDataURL('image/png')
    const exportCanvas = document.createElement('canvas')
    exportCanvas.width = Math.max(1, Math.round(canvas.width * scale))
    exportCanvas.height = Math.max(1, Math.round(canvas.height * scale))
    const ctx = exportCanvas.getContext('2d')
    if (!ctx) return canvas.toDataURL('image/png')
    ctx.imageSmoothingEnabled = false
    ctx.drawImage(canvas, 0, 0, exportCanvas.width, exportCanvas.height)
    return exportCanvas.toDataURL('image/png')
  }

  const beginErase = (event: React.PointerEvent) => {
    if (!eraserEnabled) return
    const point = pointFromEvent(event)
    if (!point) return
    event.preventDefault()
    event.stopPropagation()
    eraserDrawingRef.current = true
    lastEraserPointRef.current = point
    drawEraserStroke(point, point)
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }

  const moveErase = (event: React.PointerEvent) => {
    if (!eraserDrawingRef.current || !eraserEnabled) return
    const point = pointFromEvent(event)
    const lastPoint = lastEraserPointRef.current
    if (!point || !lastPoint) return
    event.preventDefault()
    drawEraserStroke(lastPoint, point)
    lastEraserPointRef.current = point
  }

  const endErase = (event: React.PointerEvent) => {
    if (!eraserDrawingRef.current) return
    event.preventDefault()
    event.stopPropagation()
    eraserDrawingRef.current = false
    lastEraserPointRef.current = null
    const canvas = eraserCanvasRef.current
    if (canvas && onErase) onErase(compactMaskDataUrl(canvas))
  }

  const beginDrag = (event: React.PointerEvent, mode: DragMode) => {
    if (eraserEnabled || previewOnly) return
    const point = pointFromEvent(event)
    if (!point) return
    event.preventDefault()
    event.stopPropagation()
    onEditStart?.(normalized)
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
      const startPoints = validQuadPoints(drag.start.points) ? drag.start.points : pointsFromRect(drag.start)

      if (drag.mode === 'move') {
        setTransform({
          ...drag.start,
          points: startPoints.map(startPoint => ({ x: startPoint.x + dx, y: startPoint.y + dy })) as QuadPoints,
        })
        return
      }

      if (drag.mode === 'rotate') {
        const center = quadCenter(startPoints)
        const startAngle = Math.atan2(drag.startY - center.y, drag.startX - center.x)
        const nextAngle = Math.atan2(point.y - center.y, point.x - center.x)
        const delta = nextAngle - startAngle
        setTransform({
          ...drag.start,
          points: rotatePoints(startPoints, center, delta),
          rotation: (drag.start.rotation || 0) + (delta * 180) / Math.PI,
        })
        return
      }

      if (drag.mode === 'skew-x') {
        const points = startPoints.map(startPoint => ({ ...startPoint })) as QuadPoints
        points[0] = { ...points[0], x: points[0].x + dx }
        points[1] = { ...points[1], x: points[1].x + dx }
        setTransform({ ...drag.start, points, skewX: (drag.start.skewX || 0) + (dx / Math.max(1, imageSize.width)) * 180 })
        return
      }

      if (drag.mode === 'skew-y') {
        const points = startPoints.map(startPoint => ({ ...startPoint })) as QuadPoints
        points[1] = { ...points[1], y: points[1].y + dy }
        points[2] = { ...points[2], y: points[2].y + dy }
        setTransform({ ...drag.start, points, skewY: (drag.start.skewY || 0) + (dy / Math.max(1, imageSize.height)) * 180 })
        return
      }

      if (drag.mode === "edge-top" || drag.mode === "edge-right" || drag.mode === "edge-bottom" || drag.mode === "edge-left") {
        setTransform({ ...drag.start, points: moveEdge(startPoints, drag.mode, dx, dy, imageSize) })
        return
      }

      const cornerIndex = Number(drag.mode.replace('corner-', ''))
      if (cornerIndex >= 0 && cornerIndex < 4) {
        if (event.shiftKey) {
          const anchorIndex = (cornerIndex + 2) % 4
          setTransform({ ...drag.start, points: scalePointsFromAnchor(startPoints, anchorIndex, cornerIndex, point) })
          return
        }
        const points = startPoints.map(startPoint => ({ ...startPoint })) as QuadPoints
        points[cornerIndex] = { x: point.x, y: point.y }
        setTransform({ ...drag.start, points })
      }
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

  const points = normalized.points ?? pointsFromRect(normalized)
  const bbox = boundingBoxFromPoints(points, imageSize)
  const polygonPoints = points.map(point => `${(point.x / imageSize.width) * 100},${(point.y / imageSize.height) * 100}`).join(' ')
  const relativePolygon = points.map(point => {
    const x = bbox.width > 0 ? ((point.x - bbox.x) / bbox.width) * 100 : 0
    const y = bbox.height > 0 ? ((point.y - bbox.y) / bbox.height) * 100 : 0
    return `${round(x)}% ${round(y)}%`
  }).join(', ')
  const center = quadCenter(points)
  const topCenter = midpoint(points[0], points[1])
  const rightCenter = midpoint(points[1], points[2])
  const bottomCenter = midpoint(points[2], points[3])
  const leftCenter = midpoint(points[3], points[0])
  const edgeHandlePoints = [topCenter, rightCenter, bottomCenter, leftCenter]
  const topSkewHandle = { x: topCenter.x, y: topCenter.y - Math.max(16, imageSize.height * 0.022) }
  const rightSkewHandle = { x: rightCenter.x + Math.max(16, imageSize.width * 0.022), y: rightCenter.y }
  const rotateHandle = { x: topCenter.x, y: topCenter.y - Math.max(42, imageSize.height * 0.058) }

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-transparent" style={{ aspectRatio: `${imageSize.width} / ${imageSize.height}` }}>
      <div ref={containerRef} className="relative h-full w-full touch-none select-none" style={{ cursor: eraserEnabled ? ERASER_CURSOR : previewOnly ? 'default' : undefined }}>
        {imageUrl ? (
          <img
            src={imageUrl}
            alt="Generated preview"
            className="h-full w-full object-fill"
            onLoad={event => {
              const img = event.currentTarget
              const nextSize = { width: img.naturalWidth || imageSize.width, height: img.naturalHeight || imageSize.height }
              setImageSize(nextSize)
            }}
          />
        ) : <div className="h-full w-full bg-[#1A1A1A]" />}

        {staticLayers.map(layer => {
          if (!layer.componentImageUrl) return null
          const box = layerBox(layer.transform, imageSize)
          return (
            <div
              key={layer.transform.componentKey + ":" + layer.label}
              className={layer.onSelect ? "absolute cursor-pointer overflow-hidden" : "pointer-events-none absolute overflow-hidden"}
              onPointerDown={event => {
                if (!layer.onSelect) return
                event.preventDefault()
                event.stopPropagation()
                layer.onSelect()
              }}
              style={{
                left: String((box.bbox.x / imageSize.width) * 100) + "%",
                top: String((box.bbox.y / imageSize.height) * 100) + "%",
                width: String((box.bbox.width / imageSize.width) * 100) + "%",
                height: String((box.bbox.height / imageSize.height) * 100) + "%",
                clipPath: "polygon(" + box.relativePolygon + ")",
              }}
            >
              <img src={layer.componentImageUrl} alt={layer.label} className="h-full w-full object-fill" draggable={false} />
            </div>
          )
        })}

        {componentImageUrl ? (
          <div
            className="pointer-events-none absolute overflow-hidden"
            style={{
              left: `${(bbox.x / imageSize.width) * 100}%`,
              top: `${(bbox.y / imageSize.height) * 100}%`,
              width: `${(bbox.width / imageSize.width) * 100}%`,
              height: `${(bbox.height / imageSize.height) * 100}%`,
              clipPath: `polygon(${relativePolygon})`,
            }}
          >
            <img
              src={componentImageUrl}
              alt={label}
              className="h-full w-full object-fill"
              draggable={false}
              onLoad={event => rememberAssetAspectRatio(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)}
            />
          </div>
        ) : null}

        {!previewOnly && (
        <svg className="pointer-events-none absolute inset-0 h-full w-full overflow-visible" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label={`${label} perspective quad`}>
          <polygon points={polygonPoints} fill="rgba(20,80,245,0.08)" stroke="white" strokeWidth="0.45" vectorEffect="non-scaling-stroke" />
          <polygon
            points={polygonPoints}
            fill="transparent"
            stroke="#1450F5"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
            className="pointer-events-auto cursor-move"
            onPointerDown={event => beginDrag(event, 'move')}
          />
        </svg>
        )}

        {eraserEnabled && !previewOnly ? (
          <canvas
            ref={eraserCanvasRef}
            className="absolute inset-0 z-20 h-full w-full opacity-70 mix-blend-multiply"
            style={{ cursor: ERASER_CURSOR }}
            onPointerDown={beginErase}
            onPointerMove={moveErase}
            onPointerUp={endErase}
            onPointerCancel={endErase}
            aria-label="Magic Eraser mask"
          />
        ) : null}

        {!previewOnly && (
        <div
          className="pointer-events-none absolute rounded-[3px] bg-[#0A0A0A]/85 px-1.5 py-0.5 text-[10px] font-medium text-white"
          style={{ left: `${(center.x / imageSize.width) * 100}%`, top: `${(center.y / imageSize.height) * 100}%`, transform: 'translate(-50%, -50%)' }}
        >
          {label}
        </div>
        )}

        {!eraserEnabled && !previewOnly ? (
          <>
            <button
              type="button"
              onPointerDown={event => beginDrag(event, 'rotate')}
              className="absolute z-10 flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 cursor-grab items-center justify-center rounded-full border-2 border-white bg-[#1450F5] text-[12px] font-semibold leading-none text-white shadow"
              style={{ left: `${(rotateHandle.x / imageSize.width) * 100}%`, top: `${(rotateHandle.y / imageSize.height) * 100}%` }}
              aria-label="Rotate"
              title="Rotate"
            >
              R
            </button>
            <button
              type="button"
              onPointerDown={event => beginDrag(event, 'skew-x')}
              className="absolute z-10 h-4 w-8 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize rounded-full border-2 border-white bg-[#1450F5] shadow"
              style={{ left: `${(topSkewHandle.x / imageSize.width) * 100}%`, top: `${(topSkewHandle.y / imageSize.height) * 100}%` }}
              aria-label="Skew horizontally"
              title="Skew horizontally"
            />
            <button
              type="button"
              onPointerDown={event => beginDrag(event, 'skew-y')}
              className="absolute z-10 h-8 w-4 -translate-x-1/2 -translate-y-1/2 cursor-ns-resize rounded-full border-2 border-white bg-[#1450F5] shadow"
              style={{ left: `${(rightSkewHandle.x / imageSize.width) * 100}%`, top: `${(rightSkewHandle.y / imageSize.height) * 100}%` }}
              aria-label="Skew vertically"
              title="Skew vertically"
            />
          </>
        ) : null}

        {!eraserEnabled && !previewOnly && EDGE_HANDLES.map((handle, index) => {
          const point = edgeHandlePoints[index]
          return (
            <button
              key={handle.mode}
              type="button"
              onPointerDown={event => beginDrag(event, handle.mode)}
              className={`absolute z-10 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-[3px] border-2 border-white bg-[#1450F5] shadow ${handle.cursor}`}
              style={{ left: `${(point.x / imageSize.width) * 100}%`, top: `${(point.y / imageSize.height) * 100}%` }}
              aria-label={`${handle.label} resize`}
              title={`${handle.label} resize`}
            />
          )
        })}

        {!eraserEnabled && !previewOnly && points.map((corner, index) => (
          <button
            key={CORNERS[index].label}
            type="button"
            onPointerDown={event => beginDrag(event, `corner-${index}` as DragMode)}
            className={`absolute z-10 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-[#1450F5] shadow ${CORNERS[index].cursor}`}
            style={{ left: `${(corner.x / imageSize.width) * 100}%`, top: `${(corner.y / imageSize.height) * 100}%` }}
            aria-label={`${CORNERS[index].label} corner`}
            title={`${CORNERS[index].label} corner`}
          />
        ))}
      </div>
    </div>
  )
}
