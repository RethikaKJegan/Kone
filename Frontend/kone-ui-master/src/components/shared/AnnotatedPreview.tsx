import { cn } from '../../lib/utils'
import type { ComponentPin, ComponentKey } from '../../types'

interface Props {
  imageUrl: string | null
  pins: ComponentPin[]
  annotationsEnabled: boolean
  activeFilters: ComponentKey[]
  labels: Record<ComponentKey, string>
}

export function AnnotatedPreview({ imageUrl, pins, annotationsEnabled, activeFilters, labels }: Props) {
  const visiblePins = pins.filter(
    p => annotationsEnabled && activeFilters.includes(p.componentKey)
  )

  return (
    <div className="relative w-full overflow-hidden rounded-lg bg-[#F5F5F5]" style={{ aspectRatio: '4/3' }}>
      {imageUrl ? (
        <img
          src={imageUrl}
          alt="Uploaded building"
          className="w-full h-full object-cover"
        />
      ) : (
        <div className="w-full h-full bg-[#E4E4E4]" />
      )}

      {visiblePins.map(pin => (
        <div
          key={pin.componentKey}
          className="absolute"
          style={{ left: `${pin.x}%`, top: `${pin.y}%` }}
        >
          <div
            className={cn(
              'absolute -translate-x-1/2 -translate-y-full mb-1 flex flex-col gap-0.5 rounded-[4px] bg-[rgba(10,10,10,0.85)] px-2 py-1.5 text-white',
              'bottom-3'
            )}
          >
            <span className="text-[11px] font-semibold uppercase tracking-wide">
              {labels[pin.componentKey]}
            </span>
            <span className="text-[11px] text-white/50">Generated component</span>
          </div>
          <div
            className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-[rgba(10,10,10,0.85)] bg-white"
            style={{ width: 6, height: 6 }}
            aria-hidden="true"
          />
        </div>
      ))}
    </div>
  )
}
