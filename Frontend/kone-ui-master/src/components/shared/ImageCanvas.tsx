import { useState, useRef } from 'react'
import { ZoomIn, ZoomOut } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { ComponentPin, ComponentKey } from '../../types'

interface Props {
  imageUrl: string | null
  pins: ComponentPin[]
  selectedComponent: ComponentKey | null
  labels: Record<ComponentKey, string>
  onPinMove: (componentKey: ComponentKey, x: number, y: number) => void
  showAnnotations?: boolean
}

export function ImageCanvas({ imageUrl, pins, selectedComponent, labels, onPinMove, showAnnotations = true }: Props) {
  const [zoom, setZoom] = useState(1)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleCanvasClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!selectedComponent) return
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = ((e.clientX - rect.left) / rect.width) * 100
    const y = ((e.clientY - rect.top) / rect.height) * 100
    onPinMove(selectedComponent, Math.round(x), Math.round(y))
  }

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-[#0A0A0A]" style={{ aspectRatio: '4/3' }}>
      <div
        ref={containerRef}
        onClick={handleCanvasClick}
        className={cn(
          'relative w-full h-full',
          selectedComponent ? 'cursor-crosshair' : 'cursor-default'
        )}
        style={{ transform: `scale(${zoom})`, transformOrigin: 'center center', transition: 'transform 0.15s' }}
        role="img"
        aria-label="Component placement canvas — click to reposition selected component"
      >
        {imageUrl ? (
          <img src={imageUrl} alt="Building" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full bg-[#1A1A1A]" />
        )}

        {pins.map(pin => {
          const isSelected = pin.componentKey === selectedComponent
          return (
            <div
              key={pin.componentKey}
              className="absolute transition-opacity duration-200"
              style={{ left: `${pin.x}%`, top: `${pin.y}%` }}
              aria-label={`${labels[pin.componentKey]} pin at ${pin.x}% ${pin.y}%`}
            >
              <div className="relative -translate-x-1/2 -translate-y-full">
                {showAnnotations && (
                  <div className="mb-1 flex items-center gap-1 rounded-[4px] bg-[rgba(10,10,10,0.88)] px-2 py-0.5 text-[11px] font-medium text-white whitespace-nowrap shadow-lg">
                    {pin.aiPlaced && <span className="text-[#1450F5]">✦</span>}
                    {labels[pin.componentKey]}
                  </div>
                )}
              </div>
              <div
                className={cn(
                  'absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 transition-colors duration-[120ms]',
                  isSelected
                    ? 'border-[#1450F5] bg-[#1450F5]'
                    : 'border-white bg-[#1450F5]'
                )}
                style={{ width: 8, height: 8 }}
              />
            </div>
          )
        })}
      </div>

      <div className="absolute bottom-3 right-3 flex flex-col gap-1">
        <button
          onClick={() => setZoom(z => Math.min(z + 0.25, 3))}
          aria-label="Zoom in"
          className="flex items-center justify-center rounded-[4px] bg-white/90 text-[#525252] transition-colors duration-[120ms] hover:bg-white"
          style={{ width: 28, height: 28 }}
        >
          <ZoomIn style={{ width: 14, height: 14 }} />
        </button>
        <button
          onClick={() => setZoom(z => Math.max(z - 0.25, 0.5))}
          aria-label="Zoom out"
          className="flex items-center justify-center rounded-[4px] bg-white/90 text-[#525252] transition-colors duration-[120ms] hover:bg-white"
          style={{ width: 28, height: 28 }}
        >
          <ZoomOut style={{ width: 14, height: 14 }} />
        </button>
      </div>
    </div>
  )
}
