import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, RotateCcw } from 'lucide-react'
import { isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { ImageCanvas } from '../../../components/shared/ImageCanvas'
import { AIBadge } from '../../../components/shared/AIBadge'
import { KONE_COMPONENTS } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import { cn } from '../../../lib/utils'
import type { ComponentKey, ComponentPin } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>

export default function Step4Repin() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, runAIPlacement, setPins, goToStep } = useOfferingStore()
  const [selectedComp, setSelectedComp] = useState<ComponentKey | null>(null)

  const offering = currentOffering
  const components = offering?.selectedComponents ?? []
  const pins = offering?.componentPins ?? []

  if (isGuestSession() && !offering?.renderComplete) {
    return (
      <div className="rounded-xl border border-[#E9ECEF] bg-white p-8 shadow-sm">
        <h2 className="text-heading text-[15px] font-semibold text-[#111827]">4 &nbsp; Adjust Placement</h2>
        <p className="mt-4 text-sm text-[#6B7280]">Preview is still being generated.</p>
      </div>
    )
  }

  const handlePinMove = (componentKey: ComponentKey, x: number, y: number) => {
    const newPins = pins.map(p =>
      p.componentKey === componentKey ? { ...p, x, y, aiPlaced: false } : p
    )
    const exists = newPins.find(p => p.componentKey === componentKey)
    if (!exists) newPins.push({ componentKey, x, y, aiPlaced: false })
    setPins(newPins)
    setSelectedComp(null)
  }

  const handleRestore = async () => {
    setPins([])
    await runAIPlacement()
    toast('Components restored to AI placement')
  }

  const handleContinue = () => {
    goToStep(5)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
    goToStep(3)
  }

  const handleSkip = () => {
    goToStep(5)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
  }

  return (
    <div className="overflow-hidden rounded-xl border border-[#E9ECEF] bg-white shadow-sm">
      <div className="flex items-start justify-between px-8 pb-2 pt-8">
        <div>
          <h2 className="text-heading text-[15px] font-semibold text-[#111827]">4 &nbsp; Adjust Placement</h2>
          <p className="mt-1 text-[12px] text-[#9CA3AF]">Optional — click a component then click the image to reposition its pin</p>
        </div>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
      </div>

      <div className="flex gap-0 border-t border-[#E9ECEF] mt-4">
        {/* Canvas */}
        <div className="relative flex-[3] p-6 pr-3">
          <ImageCanvas
            imageUrl={offering?.outputImageUrl ?? offering?.uploadedFileUrl ?? null}
            pins={pins}
            selectedComponent={selectedComp}
            labels={COMP_LABELS}
            onPinMove={handlePinMove}
          />
        </div>

        {/* Right panel */}
        <div className="flex flex-[2] flex-col border-l border-[#E9ECEF] p-6 pl-4">
          <p className="label-caps mb-4">Component Placement</p>

          <div className="flex-1 space-y-2">
            {components.map(comp => {
              const pin = pins.find((p: ComponentPin) => p.componentKey === comp)
              const isActive = selectedComp === comp
              return (
                <div
                  key={comp}
                  className={cn(
                    'rounded-lg border p-3 transition-colors duration-[120ms]',
                    isActive ? 'border-[#0A0A0A] bg-[#FAFAFA]' : 'border-[#E4E4E4] bg-white'
                  )}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      <div className="shrink-0 rounded bg-[#F5F5F5]" style={{ width: 28, height: 28 }} />
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-xs font-semibold text-[#0A0A0A]">{COMP_LABELS[comp]}</span>
                          {pin?.aiPlaced && <AIBadge />}
                        </div>
                        {pin ? (
                          <p className="truncate text-[11px] text-[#A3A3A3]">
                            {pin.aiPlaced ? '✦ AI · ' : ''}X {pin.x} · Y {pin.y}
                          </p>
                        ) : (
                          <p className="text-[11px] text-[#A3A3A3]">Not placed</p>
                        )}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      {pin && <Check className="text-[#16A34A]" style={{ width: 14, height: 14 }} />}
                      <button
                        onClick={() => setSelectedComp(prev => prev === comp ? null : comp)}
                        className={cn(
                          'text-[11px] font-medium transition-colors duration-[120ms]',
                          isActive ? 'text-[#0A0A0A]' : 'text-[#525252] hover:text-[#0A0A0A]'
                        )}
                        aria-label={`Repin ${COMP_LABELS[comp]}`}
                      >
                        {isActive ? 'Cancel' : 'Repin'}
                      </button>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          <button
            onClick={handleRestore}
            className="mt-3 flex items-center gap-1.5 text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]"
          >
            <RotateCcw style={{ width: 13, height: 13 }} />
            Restore to AI placement
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-[#E4E4E4] px-8 py-5">
        <button
          onClick={handleSkip}
          className="text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252]"
        >
          Skip this step
        </button>
        <button
          onClick={handleContinue}
          className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626]"
          style={{ height: 34 }}
        >
          Apply & Continue
        </button>
      </div>
    </div>
  )
}
