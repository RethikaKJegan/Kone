import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Sparkles, Check, RotateCcw, Eye, EyeOff } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { ImageCanvas } from '../../../components/shared/ImageCanvas'
import { AIBadge } from '../../../components/shared/AIBadge'
import { Skeleton } from '../../../components/ui/skeleton'
import { KONE_COMPONENTS } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import type { ComponentKey, ComponentPin } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>

export default function Step3Place() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, runAIPlacement, setPins, setCurrentOffering, goToStep, isProcessing } = useOfferingStore()
  const [hasRunAI, setHasRunAI] = useState(false)
  const [showAnnotations, setShowAnnotations] = useState(true)

  const offering = currentOffering
  const components = offering?.selectedComponents ?? []
  const pins = offering?.componentPins ?? []
  const previewReady = !isGuestSession() || !!(offering?.renderComplete && offering.outputImageUrl)

  useEffect(() => {
    if (!previewReady) return
    if (!hasRunAI && components.length > 0 && pins.length === 0) {
      setHasRunAI(true)
      runAIPlacement().then(() => toast('Components placed by AI'))
    } else if (pins.length > 0) {
      setHasRunAI(true)
    }
  }, [previewReady])

  useEffect(() => {
    let stopped = false
    async function poll() {
      if (!projectId || !currentOffering || !isGuestSession()) return
      const sessionId = await getGuestSessionId()
      while (!stopped) {
        const { data } = await apiClient.get('/guest/status', {
          params: { session_id: sessionId, project_id: projectId },
        })
        if (data.status === 'preview_ready') {
          setCurrentOffering({ ...currentOffering, outputImageUrl: `${data.preview_url}?v=${Date.now()}`, renderComplete: true, componentPins: [] })
          return
        }
        if (data.status === 'failed') {
          toast(data.error || 'Preview generation failed')
          return
        }
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }
    poll()
    return () => {
      stopped = true
    }
  }, [projectId, currentOffering?.id])

  const handleRestore = async () => {
    setPins([])
    setHasRunAI(false)
    await runAIPlacement()
    toast('Components placed by AI')
  }

  const allPlaced = components.every(k => pins.some(p => p.componentKey === k))
  const placedCount = components.filter(k => pins.some(p => p.componentKey === k)).length

  const handleContinue = () => {
    goToStep(4)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/4`)
  }

  const handleAdjustPlacement = () => {
    goToStep(4)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/4`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/2`)
    goToStep(2)
  }

  if (!previewReady) {
    return (
      <div className="kone-enter overflow-hidden rounded-xl border border-[#E9ECEF] bg-white shadow-sm">
        <div className="flex items-start justify-between px-8 pb-4 pt-8">
          <h2 className="text-heading text-[15px] font-semibold text-[#111827]">3 &nbsp; Preview</h2>
          <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
        </div>
        <div className="mx-8 mb-8 flex min-h-[360px] flex-col items-center justify-center gap-4 rounded-lg border border-[#E4E4E4] bg-white">
          <div className="h-7 w-7 animate-spin rounded-full border-2 border-[#DBEAFE] border-t-[#1450F5]" />
          <p className="text-sm font-medium text-[#111827]">Generating final preview...</p>
          <p className="text-xs text-[#9CA3AF]">The preview appears here after the Python pipeline is complete.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="kone-enter overflow-hidden rounded-xl border border-[#E9ECEF] bg-white shadow-sm">
      <div className="flex items-start justify-between px-8 pb-4 pt-8">
        <h2 className="text-heading text-[15px] font-semibold text-[#111827]">3 &nbsp; Preview</h2>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
      </div>

      {/* AI status banner */}
      <div className="mx-8 mb-4 flex items-start gap-3 rounded-lg border border-[#DBEAFE] bg-[#EFF6FF] px-4 py-3">
        <Sparkles className="shrink-0 text-[#1450F5] mt-0.5" style={{ width: 15, height: 15 }} />
        <div>
          <p className="text-sm font-medium text-[#1e3a5f]">AI has pre-placed all components based on spatial intelligence.</p>
          <p className="mt-0.5 text-xs text-[#3b82f6]">✦ pins are AI-placed. Use the optional step to manually adjust placement.</p>
        </div>
      </div>

      <div className="flex gap-0 border-t border-[#E9ECEF]">
        {/* Canvas */}
        <div className="relative flex-[3] p-6 pr-3">
          {isProcessing ? (
            <div className="relative">
              <Skeleton className="w-full rounded-lg" style={{ aspectRatio: '4/3' }} />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="h-7 w-7 animate-spin rounded-full border-2 border-[#DBEAFE] border-t-[#1450F5]" />
              </div>
            </div>
          ) : (
            <ImageCanvas
              imageUrl={offering?.outputImageUrl ?? offering?.uploadedFileUrl ?? null}
              pins={pins}
              selectedComponent={null}
              labels={COMP_LABELS}
              onPinMove={() => {}}
              showAnnotations={showAnnotations}
            />
          )}
        </div>

        {/* Right panel */}
        <div className="flex flex-[2] flex-col border-l border-[#E4E4E4] p-6 pl-4">
          <div className="mb-4 flex items-center justify-between">
            <span className="text-xs text-[#A3A3A3]">{placedCount}/{components.length} placed</span>
            <button
              onClick={() => setShowAnnotations(v => !v)}
              className="flex items-center gap-1.5 rounded-[4px] border border-[#E4E4E4] px-2.5 py-1 text-[11px] font-medium text-[#525252] transition-all duration-[150ms] hover:border-[#1450F5] hover:text-[#1450F5]"
            >
              {showAnnotations
                ? <><Eye style={{ width: 12, height: 12 }} /> Annotations on</>
                : <><EyeOff style={{ width: 12, height: 12 }} /> Annotations off</>
              }
            </button>
          </div>

          <div className="flex-1 space-y-2">
            {isProcessing
              ? components.map(k => <Skeleton key={k} className="h-14 rounded-lg" />)
              : components.map(comp => {
                  const pin = pins.find((p: ComponentPin) => p.componentKey === comp)
                  return (
                    <div
                      key={comp}
                      className="rounded-lg border border-[#E4E4E4] bg-white p-3 transition-all duration-200 hover:border-[#BFDBFE] hover:shadow-sm"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <div className="shrink-0 rounded bg-[#EFF6FF]" style={{ width: 28, height: 28 }} />
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
                        {pin && <Check className="shrink-0 text-[#16A34A]" style={{ width: 14, height: 14 }} />}
                      </div>
                    </div>
                  )
                })}
          </div>

          {allPlaced && !isProcessing && (
            <p className="mt-3 text-xs font-medium text-[#16A34A]">All components placed — ready to continue</p>
          )}

          <button
            onClick={handleRestore}
            disabled={isProcessing}
            className="mt-3 flex items-center gap-1.5 text-xs text-[#A3A3A3] transition-colors duration-[120ms] hover:text-[#525252] disabled:opacity-40"
          >
            <RotateCcw style={{ width: 13, height: 13 }} />
            Restore to default
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between border-t border-[#E4E4E4] px-8 py-5">
        <button
          onClick={handleAdjustPlacement}
          disabled={!allPlaced || isProcessing}
          className="text-xs text-[#6B7280] transition-colors duration-[120ms] hover:text-[#1450F5] disabled:opacity-40"
        >
          Adjust placement (optional) →
        </button>
        <button
          onClick={handleContinue}
          disabled={!allPlaced}
          className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 34 }}
        >
          Continue →
        </button>
      </div>
    </div>
  )
}
