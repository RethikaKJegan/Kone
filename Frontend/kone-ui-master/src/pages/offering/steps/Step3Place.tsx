import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Sparkles, Check, RotateCcw, Eye, EyeOff, Move } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { ImageCanvas } from '../../../components/shared/ImageCanvas'
import { AIBadge } from '../../../components/shared/AIBadge'
import { Skeleton } from '../../../components/ui/skeleton'
import { componentDisplayLabel } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import { safeSystemErrorMessage } from '../../../lib/safeErrors'
import type { ComponentKey, ComponentPin } from '../../../types'

const COMPONENT_LABEL_KEYS: ComponentKey[] = ['ceiling', 'kds', 'kds_2', 'kds_3', 'dcs1020', 'lci', 'door', 'cop']
const COMP_LABELS = Object.fromEntries(COMPONENT_LABEL_KEYS.map(key => [key, componentDisplayLabel(key)])) as Record<ComponentKey, string>
function formatPreviewTime(seconds: number) {
  if (seconds <= 0) return 'less than 1 sec'
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes <= 0) return remainingSeconds + ' sec'
  if (remainingSeconds <= 0) return minutes + ' min'
  return minutes + ' min ' + remainingSeconds + ' sec'
}

export default function Step3Place() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, runAIPlacement, setCurrentOffering, goToStep, isProcessing } = useOfferingStore()
  const [hasRunAI, setHasRunAI] = useState(false)
  const [showAnnotations, setShowAnnotations] = useState(true)
  const [previewElapsedSeconds, setPreviewElapsedSeconds] = useState(0)

  const offering = currentOffering
  const components = offering?.selectedComponents ?? []
  const pins = offering?.componentPins ?? []
  const previewReady = !!(
    offering?.outputImageUrl &&
    (offering.renderComplete || offering.pipelineStatus === 'preview_ready' || offering.pipelineStatus === 'video_ready')
  )
  useEffect(() => {
    if (previewReady) {
      setPreviewElapsedSeconds(0)
      return
    }
    setPreviewElapsedSeconds(0)
    const timer = window.setInterval(() => {
      setPreviewElapsedSeconds(seconds => seconds + 1)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [previewReady, currentOffering?.previewRequestKey])

  useEffect(() => {
    if (!previewReady) return
    if (!isGuestSession()) {
      setHasRunAI(true)
      return
    }
    if (!hasRunAI && components.length > 0 && pins.length === 0) {
      setHasRunAI(true)
      runAIPlacement().then(placedPins => {
        toast(placedPins.length === components.length ? 'Components placed by AI' : 'Some components need placement')
      })
    } else if (pins.length > 0) {
      setHasRunAI(true)
    }
  }, [previewReady])

  useEffect(() => {
    let stopped = false
    async function poll() {
      if (!projectId || !offeringId || !currentOffering) return
      const guest = isGuestSession()
      const sessionId = guest ? await getGuestSessionId() : null
      while (!stopped) {
        if (guest) {
          const { data } = await apiClient.get('/guest/status', {
            params: { session_id: sessionId, project_id: projectId },
          })
          if (data.status === 'preview_ready') {
            if (data.preview_request_key && data.preview_request_key !== currentOffering.previewRequestKey) {
              await new Promise(resolve => setTimeout(resolve, 2000))
              continue
            }
            setCurrentOffering({
              ...currentOffering,
              outputImageUrl: `${data.preview_url}?v=${Date.now()}`,
              outputVideoUrl: null,
              renderComplete: true,
              pipelineStatus: 'preview_ready',
              videoGenerated: false,
              downloadUrl: null,
              componentPins: data.component_pins ?? [],
              previewVersions: data.preview_versions ?? currentOffering.previewVersions,
            })
            return
          }
          if (data.status === 'failed') {
            if (data.preview_request_key && data.preview_request_key !== currentOffering.previewRequestKey) {
              await new Promise(resolve => setTimeout(resolve, 2000))
              continue
            }
            toast(safeSystemErrorMessage(), 'destructive')
            return
          }
        } else {
          const { data } = await apiClient.get(`/offerings/${offeringId}`)
          if (data.previewRequestKey && data.previewRequestKey !== currentOffering.previewRequestKey) {
            await new Promise(resolve => setTimeout(resolve, 2000))
            continue
          }
          if (data.pipelineStatus === 'preview_ready' || data.pipelineStatus === 'video_ready') {
            const outputVideoUrl = data.pipelineStatus === 'video_ready'
              ? data.outputVideoUrl ?? data.outputVideoPath ?? currentOffering.outputVideoUrl ?? null
              : null
            setCurrentOffering({
              ...data,
              renderComplete: true,
              outputImageUrl: data.outputImageUrl ? data.outputImageUrl + (data.outputImageUrl.includes('?') ? '&' : '?') + 'v=' + Date.now() : null,
              outputVideoUrl,
              videoGenerated: data.pipelineStatus === 'video_ready' ? Boolean(outputVideoUrl || data.videoGenerated) : false,
              downloadUrl: data.pipelineStatus === 'video_ready' ? data.downloadUrl ?? currentOffering.downloadUrl ?? null : null,
            })
            return
          }
          if (data.pipelineStatus === 'failed') {
            setCurrentOffering({ ...data, renderComplete: false })
            toast(safeSystemErrorMessage(), 'destructive')
            return
          }
        }
        await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }
    poll()
    return () => {
      stopped = true
    }
  }, [projectId, currentOffering?.id, currentOffering?.previewRequestKey])

  const handleRestore = () => {
    if (!projectId || !offeringId || !offering || offering.projectId !== projectId || offering.id !== offeringId) {
      toast('Visualization state is not ready. Please reopen this visualization.', 'destructive')
      return
    }
    goToStep(1)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/1`, {
      state: { restoreToDefault: true, projectId, offeringId },
    })
  }

  const allPlaced = components.every(k => pins.some(p => p.componentKey === k))
  const placedCount = components.filter(k => pins.some(p => p.componentKey === k)).length
  const hasMissingPlacements = components.length > 0 && !allPlaced
  const previewStepVersion = offering?.previewVersions?.find(version => Number(version.version) === 1)
  const previewStepImageUrl = previewStepVersion?.url ?? offering?.outputImageUrl ?? offering?.uploadedFileUrl ?? null

  const handleContinue = () => {
    goToStep(5)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
  }

  const handleRepin = () => {
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
          <div className="w-full max-w-[320px] space-y-2">
            <div className="h-2 overflow-hidden rounded-full bg-[#E5E7EB]">
              <div className="h-full w-full animate-pulse rounded-full bg-[#1450F5]" />
            </div>
            <p className="text-center text-xs text-[#6B7280]">Elapsed time: {formatPreviewTime(previewElapsedSeconds)}</p>
          </div>
          <p className="text-xs text-[#9CA3AF]">The preview appears here after the process is complete.</p>
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
          <p className="text-sm font-medium text-[#1e3a5f]">
            {hasMissingPlacements ? 'AI placed the detected components from the generated preview.' : 'AI has pre-placed all components based on spatial intelligence.'}
          </p>
          <p className="mt-0.5 text-xs text-[#3b82f6]">
            {hasMissingPlacements ? 'Some selected components need review before continuing.' : 'Final preview is ready.'}
          </p>
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
              imageUrl={previewStepImageUrl}
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

      <div className="flex items-center justify-between gap-3 border-t border-[#E4E4E4] px-8 py-5">
        <button
          onClick={handleRepin}
          disabled={!allPlaced}
          className="flex items-center gap-1.5 rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626] disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 36 }}
        >
          <Move style={{ width: 14, height: 14 }} />
          Repin
        </button>
        <button
          onClick={handleContinue}
          disabled={!allPlaced}
          className="rounded-[5px] bg-[#0A0A0A] px-5 text-sm font-medium text-white transition-colors duration-[120ms] hover:bg-[#262626] disabled:cursor-not-allowed disabled:opacity-40"
          style={{ height: 36 }}
        >
          Continue to Video →
        </button>
      </div>
    </div>
  )
}
