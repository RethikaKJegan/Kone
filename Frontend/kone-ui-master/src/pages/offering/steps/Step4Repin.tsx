import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, ChevronDown, Eye, RotateCcw, Wand2 } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { RepinTransformCanvas, repinTransformFromPin } from '../../../components/shared/RepinTransformCanvas'
import { KONE_COMPONENTS } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import { cn } from '../../../lib/utils'
import type { ComponentKey, ComponentPin, PreviewVersion, RepinFeedbackOption, RepinTransform } from '../../../types'

const COMP_LABELS = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.label])) as Record<ComponentKey, string>
const COMP_IMAGES = Object.fromEntries(KONE_COMPONENTS.map(c => [c.key, c.imageUrl ?? null])) as Record<ComponentKey, string | null>
const FEEDBACK_OPTIONS: { value: RepinFeedbackOption; label: string }[] = [
  { value: 'edge_alignment', label: 'Sharper edge alignment' },
  { value: 'perspective_depth', label: 'Better perspective depth' },
  { value: 'lighting_shadow', label: 'Match lighting and shadows' },
  { value: 'material_reflections', label: 'Improve material reflections' },
  { value: 'seamless_blending', label: 'Blend naturally into scene' },
]

function versionUrl(version: PreviewVersion | undefined, fallback: string | null | undefined) {
  return version?.url ?? fallback ?? null
}

export default function Step4Repin() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setCurrentOffering, setRepinTransforms, submitRepinPreview, goToStep, isProcessing } = useOfferingStore()
  const offering = currentOffering
  const selectedComponents = offering?.selectedComponents ?? []
  const components = selectedComponents.length ? selectedComponents : KONE_COMPONENTS.map(component => component.key)
  const pins = offering?.componentPins ?? []
  const versions = offering?.previewVersions?.length
    ? offering.previewVersions
    : offering?.outputImageUrl
      ? [{ version: 1, url: offering.outputImageUrl }]
      : []
  const latestVersion = versions.reduce((max, version) => Math.max(max, version.version), versions.length ? 1 : 0)
  const [selectedSourceVersion, setSelectedSourceVersion] = useState(latestVersion || 1)
  const sourceVersion = versions.some(version => version.version === selectedSourceVersion) ? selectedSourceVersion : latestVersion || 1
  const targetVersion = Math.min(latestVersion + 1, 5)
  const generationLimitReached = latestVersion >= 5
  const [selectedComp, setSelectedComp] = useState<ComponentKey | null>(selectedComponents[0] ?? components[0] ?? null)
  const selectedPin = pins.find((p: ComponentPin) => p.componentKey === selectedComp)
  const [repinTransforms, setLocalRepinTransforms] = useState<Partial<Record<ComponentKey, RepinTransform>>>(offering?.repinTransforms ?? {})
  const [feedbackOptions, setFeedbackOptions] = useState<RepinFeedbackOption[]>(['seamless_blending'])
  const [inspectedVersion, setInspectedVersion] = useState<PreviewVersion | null>(null)
  const [canvasConfirmed, setCanvasConfirmed] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  useEffect(() => {
    if (!latestVersion) return
    setSelectedSourceVersion(current => versions.some(version => version.version === current) ? current : latestVersion)
  }, [latestVersion, versions.map(version => version.version).join('|')])

  useEffect(() => {
    const component = selectedComp && components.includes(selectedComp) ? selectedComp : components[0]
    if (!component) return
    if (selectedComp !== component) setSelectedComp(component)

    let changed = false
    const nextTransforms: Partial<Record<ComponentKey, RepinTransform>> = { ...(offering?.repinTransforms ?? repinTransforms) }
    components.forEach(comp => {
      if (nextTransforms[comp]) return
      nextTransforms[comp] = repinTransformFromPin(comp, sourceVersion, targetVersion, pins.find((p: ComponentPin) => p.componentKey === comp))
      changed = true
    })
    if (changed) {
      setLocalRepinTransforms(nextTransforms)
      setRepinTransforms(nextTransforms)
    }
  }, [selectedComp, sourceVersion, targetVersion, components.join('|'), pins.map(pin => `${pin.componentKey}:${pin.x}:${pin.y}`).join('|')])

  useEffect(() => {
    if (offering?.repinTransforms && Object.keys(offering.repinTransforms).length > 0) {
      setLocalRepinTransforms(offering.repinTransforms)
    }
  }, [offering?.id])

  useEffect(() => {
    setCanvasConfirmed(false)
  }, [selectedComp, sourceVersion])

  useEffect(() => {
    let stopped = false
    async function poll() {
      if (!projectId || !offeringId || !offering?.previewRequestKey || offering.pipelineStatus !== 'processing') return
      const guest = isGuestSession()
      const sessionId = guest ? await getGuestSessionId() : null
      while (!stopped) {
        if (guest) {
          const { data } = await apiClient.get('/guest/status', { params: { session_id: sessionId, project_id: projectId } })
          if (data.preview_request_key && data.preview_request_key !== offering.previewRequestKey) {
            await new Promise(resolve => setTimeout(resolve, 2000))
            continue
          }
          if (data.status === 'preview_ready') {
            useOfferingStore.setState({ isProcessing: false })
            setCurrentOffering({
              ...offering,
              outputImageUrl: `${data.preview_url}?v=${Date.now()}`,
              outputVideoUrl: null,
              renderComplete: true,
              pipelineStatus: 'preview_ready',
              videoGenerated: false,
              downloadUrl: null,
              componentPins: data.component_pins ?? offering.componentPins,
              previewVersions: data.preview_versions
                ? [
                    ...(offering.previewVersions ?? []).filter(existing => !data.preview_versions.some((next: PreviewVersion) => next.version === existing.version)),
                    ...data.preview_versions,
                  ].sort((a, b) => a.version - b.version)
                : offering.previewVersions,
              repinPass: data.repin_pass ?? offering.repinPass,
            })
            if (data.repin_pass) setSelectedSourceVersion(data.repin_pass)
            toast('New repin preview generated')
            return
          }
          if (data.status === 'failed') {
            useOfferingStore.setState({ isProcessing: false })
            setCurrentOffering({ ...offering, pipelineStatus: 'failed', renderComplete: false, lastError: data.error })
            toast(data.error || 'Repin preview failed', 'destructive')
            return
          }
        } else {
          const { data } = await apiClient.get(`/offerings/${offeringId}`)
          if (data.previewRequestKey && data.previewRequestKey !== offering.previewRequestKey) {
            await new Promise(resolve => setTimeout(resolve, 2000))
            continue
          }
          if (data.pipelineStatus === 'preview_ready' || data.pipelineStatus === 'video_ready') {
            useOfferingStore.setState({ isProcessing: false })
            setCurrentOffering({
              ...data,
              renderComplete: true,
              outputImageUrl: data.outputImageUrl ? `${data.outputImageUrl}${data.outputImageUrl.includes('?') ? '&' : '?'}v=${Date.now()}` : null,
              outputVideoUrl: null,
              videoGenerated: false,
              downloadUrl: null,
            })
            if (data.repinPass) setSelectedSourceVersion(data.repinPass)
            toast('New repin preview generated')
            return
          }
          if (data.pipelineStatus === 'failed') {
            useOfferingStore.setState({ isProcessing: false })
            setCurrentOffering({ ...data, renderComplete: false })
            toast(data.lastError || 'Repin preview failed', 'destructive')
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
  }, [projectId, offeringId, offering?.previewRequestKey, offering?.pipelineStatus])

  const selectedSourcePreview = versions.find(v => v.version === sourceVersion)
  const previewImageUrl = useMemo(() => versionUrl(selectedSourcePreview, offering?.outputImageUrl), [selectedSourcePreview, offering?.outputImageUrl])
  const originalImageUrl = offering?.uploadedFileUrl ?? offering?.inputImagePath ?? null
  const sourceVersionComponent = selectedSourcePreview?.transform?.componentKey ?? null
  const shouldUseOriginalForPlacement = sourceVersion === 1
  const sourceBaseMode: 'original' | 'version' = shouldUseOriginalForPlacement ? 'original' : 'version'
  const editingBackgroundUrl = shouldUseOriginalForPlacement ? (originalImageUrl ?? previewImageUrl) : (previewImageUrl ?? originalImageUrl)
  const defaultTransformFor = (component: ComponentKey) => repinTransformFromPin(component, sourceVersion, targetVersion, pins.find((p: ComponentPin) => p.componentKey === component))

  const transform = selectedComp ? repinTransforms[selectedComp] ?? defaultTransformFor(selectedComp) : null

  const persistTransforms = (nextTransforms: Partial<Record<ComponentKey, RepinTransform>>) => {
    setLocalRepinTransforms(nextTransforms)
    setRepinTransforms(nextTransforms)
  }

  const handleTransformChange = (next: RepinTransform) => {
    persistTransforms({ ...repinTransforms, [next.componentKey]: next })
  }

  const handleNumericChange = (field: keyof Pick<RepinTransform, 'x' | 'y' | 'width' | 'height' | 'rotation' | 'skewX' | 'skewY'>, value: number) => {
    if (!transform || !selectedComp) return
    persistTransforms({ ...repinTransforms, [selectedComp]: { ...transform, [field]: value } })
  }

  const handleReset = () => {
    if (!selectedComp) return
    persistTransforms({ ...repinTransforms, [selectedComp]: repinTransformFromPin(selectedComp, sourceVersion, targetVersion, selectedPin) })
  }

  const handleConfirmCanvas = () => {
    if (!selectedComp || !transform) return
    if (!repinTransforms[selectedComp]) {
      persistTransforms({ ...repinTransforms, [selectedComp]: transform })
    }
    setInspectedVersion(null)
    setCanvasConfirmed(true)
  }

  const handleInspectVersion = (version: PreviewVersion) => {
    setInspectedVersion(version)
  }

  const handleEditFromVersion = (version: PreviewVersion) => {
    setSelectedSourceVersion(version.version)
    setInspectedVersion(null)
    setCanvasConfirmed(false)
    toast(`Editing from Version ${version.version}`)
  }

  const handleFeedbackChange = (option: RepinFeedbackOption) => {
    const nextOptions = feedbackOptions.includes(option)
      ? feedbackOptions.filter(item => item !== option)
      : [...feedbackOptions, option]
    if (!nextOptions.length) {
      toast('Select at least one FireRed correction.', 'destructive')
      return
    }
    setFeedbackOptions(nextOptions)
    if (!selectedComp || !transform) return
    persistTransforms({
      ...repinTransforms,
      [selectedComp]: { ...transform, feedbackOption: nextOptions[0], feedbackOptions: nextOptions },
    })
  }

  const handleGenerate = async () => {
    if (!transform || !selectedComp) return
    if (!canvasConfirmed) {
      toast('Confirm the selected component before generating a new preview.', 'destructive')
      return
    }
    if (generationLimitReached) {
      toast('Version limit reached. Choose the best saved version to continue to video.', 'destructive')
      return
    }
    if (!feedbackOptions.length) {
      toast('Select at least one FireRed correction.', 'destructive')
      return
    }
    const payload = {
      ...transform,
      componentKey: selectedComp,
      componentType: selectedComp,
      sourceVersion,
      targetVersion,
      rotation: transform.rotation || 0,
      skewX: transform.skewX || 0,
      skewY: transform.skewY || 0,
      editableLayerUrl: transform.editableLayerUrl ?? null,
      repinBackgroundUrl: transform.repinBackgroundUrl ?? null,
      repinBackgroundDisplayUrl: transform.repinBackgroundDisplayUrl ?? null,
      feedbackOption: feedbackOptions[0] ?? null,
      feedbackOptions,
      sourceBaseMode,
      sourceVersionComponent,
    }
    try {
      await submitRepinPreview(payload)
      toast('Generating repin preview with FireRed realism')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Could not start repin preview', 'destructive')
    }
  }

  const handlePrimaryAction = async () => {
    if (!canvasConfirmed) {
      handleConfirmCanvas()
      return
    }
    await handleGenerate()
  }

  const handleUseVersion = (version: PreviewVersion) => {
    if (!offering) return
    setCurrentOffering({ ...offering, outputImageUrl: version.url, previewImagePath: version.url, outputVideoUrl: null, videoGenerated: false, downloadUrl: null })
    goToStep(5)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
  }

  const handleBack = () => {
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/3`)
    goToStep(3)
  }

  if (!offering?.outputImageUrl) {
    return (
      <div className="rounded-xl border border-[#E9ECEF] bg-white p-8 shadow-sm">
        <h2 className="text-heading text-[15px] font-semibold text-[#111827]">4 &nbsp; Repin</h2>
        <p className="mt-4 text-sm text-[#6B7280]">Generate the preview before adjusting placement.</p>
      </div>
    )
  }

  return (
    <div className="overflow-hidden rounded-xl border border-[#E9ECEF] bg-white shadow-sm">
      <div className="flex items-start justify-between px-8 pb-2 pt-8">
        <div>
          <h2 className="text-heading text-[15px] font-semibold text-[#111827]">4 &nbsp; Repin</h2>
          <p className="mt-1 text-[12px] text-[#9CA3AF]">Adjust component geometry, then generate a realistic FireRed preview.</p>
        </div>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
      </div>

      <div className="mt-4 flex gap-0 border-t border-[#E9ECEF]">
        <div className="relative flex-[3] p-6 pr-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              {components.map(comp => (
                <button
                  key={comp}
                  onClick={() => { setSelectedComp(comp); setInspectedVersion(null) }}
                  className={cn(
                    'min-w-[128px] rounded-[5px] border px-3 py-2 text-left text-xs font-medium transition-colors duration-[120ms]',
                    selectedComp === comp ? 'border-[#1450F5] bg-[#EFF6FF] text-[#1450F5]' : 'border-[#E4E4E4] text-[#525252] hover:border-[#BFDBFE]'
                  )}
                >
                  <span className="block truncate">{COMP_LABELS[comp]}</span>
                </button>
              ))}
            </div>
            <span className="text-[11px] font-medium text-[#9CA3AF]">Editing Version {sourceVersion} to {targetVersion}</span>
          </div>

          {transform && selectedComp ? (
            inspectedVersion ? (
              <div className="relative flex min-h-[360px] items-center justify-center overflow-hidden rounded-lg border border-[#E4E4E4] bg-[#0A0A0A]">
                <img src={inspectedVersion.url} alt={`Version ${inspectedVersion.version}`} className="max-h-[520px] w-full object-contain" />
                <div className="absolute left-3 top-3 rounded-[4px] bg-black/70 px-2 py-1 text-[11px] font-semibold text-white">Version {inspectedVersion.version}</div>
                <div className="absolute right-3 top-3 flex gap-2">
                  <button onClick={() => handleEditFromVersion(inspectedVersion)} className="rounded-[4px] bg-[#1450F5] px-2 py-1 text-[11px] font-semibold text-white shadow-sm hover:bg-[#0B3BBF]">Edit from this version</button>
                  <button onClick={() => setInspectedVersion(null)} className="rounded-[4px] bg-white px-2 py-1 text-[11px] font-semibold text-[#111827] shadow-sm hover:text-[#1450F5]">Edit current</button>
                </div>
              </div>
            ) : (
              <RepinTransformCanvas
                imageUrl={editingBackgroundUrl}
                transform={transform}
                label={COMP_LABELS[selectedComp]}
                componentImageUrl={transform.editableLayerUrl ?? COMP_IMAGES[selectedComp] ?? null}
                onChange={handleTransformChange}
              />
            )
          ) : (
            <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-[#E4E4E4] text-sm text-[#6B7280]">Select a component to repin.</div>
          )}
          {transform && selectedComp && !canvasConfirmed && !inspectedVersion && (
            <p className="mt-3 text-xs text-[#6B7280]">Drag the component on the image, then confirm placement before generating the FireRed preview.</p>
          )}
        </div>

        <div className="flex flex-[2] flex-col border-l border-[#E9ECEF] p-6 pl-4">
          <div className="mb-4 flex items-center justify-between">
            <p className="label-caps">Repin Controls</p>
            <span className={cn('rounded-full px-2 py-1 text-[10px] font-semibold', canvasConfirmed ? 'bg-[#ECFDF5] text-[#047857]' : 'bg-[#FEF3C7] text-[#92400E]')}>
              {canvasConfirmed ? 'Placement confirmed' : 'Needs confirmation'}
            </span>
          </div>

          <div className="rounded-[6px] border border-[#E4E4E4] bg-[#FAFAFA] p-3">
            <p className="text-xs font-semibold text-[#111827]">{selectedComp ? COMP_LABELS[selectedComp] : 'Component'}</p>
            <p className="mt-1 text-[11px] leading-4 text-[#6B7280]">
              Move, resize, rotate, or skew the overlay on the active editing image.
            </p>
          </div>

          {transform && (
            <details open={advancedOpen} onToggle={event => setAdvancedOpen(event.currentTarget.open)} className="mt-4 rounded-[6px] border border-[#E4E4E4]">
              <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2 text-xs font-semibold text-[#525252]">
                Advanced Geometry
                <ChevronDown className={cn('h-3.5 w-3.5 transition-transform duration-[120ms]', advancedOpen && 'rotate-180')} />
              </summary>
              <div className="grid grid-cols-2 gap-2 border-t border-[#E4E4E4] p-3">
                {[
                  ['x', 'X Position'], ['y', 'Y Position'], ['width', 'Width'], ['height', 'Height'], ['rotation', 'Rotation'], ['skewX', 'Skew X'], ['skewY', 'Skew Y'],
                ].map(([field, label]) => (
                  <label key={field} className="text-[11px] font-medium text-[#6B7280]">
                    {label}
                    <input
                      type="number"
                      value={transform[field as keyof RepinTransform] as number}
                      onChange={event => handleNumericChange(field as keyof Pick<RepinTransform, 'x' | 'y' | 'width' | 'height' | 'rotation' | 'skewX' | 'skewY'>, Number(event.target.value))}
                      className="mt-1 h-8 w-full rounded-[4px] border border-[#E4E4E4] px-2 text-xs text-[#111827]"
                    />
                  </label>
                ))}
              </div>
            </details>
          )}

          {versions.length > 1 && !generationLimitReached && (
            <fieldset className="mt-4 space-y-2 rounded-[6px] border border-[#E4E4E4] p-3">
              <legend className="text-[11px] font-semibold text-[#525252]">Feedback</legend>
              {FEEDBACK_OPTIONS.map(option => (
                <label key={option.value} className="flex items-center gap-2 text-xs text-[#525252]">
                  <input type="checkbox" checked={feedbackOptions.includes(option.value)} onChange={() => handleFeedbackChange(option.value)} />
                  {option.label}
                </label>
              ))}
            </fieldset>
          )}

          <div className="mt-5 flex items-center gap-2">
            <button
              onClick={handlePrimaryAction}
              disabled={isProcessing || generationLimitReached || !transform}
              className={cn(
                'flex h-9 flex-1 items-center justify-center gap-1.5 rounded-[5px] px-4 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-40',
                canvasConfirmed ? 'bg-[#0A0A0A]' : 'bg-[#1450F5]'
              )}
            >
              {canvasConfirmed ? <Wand2 style={{ width: 13, height: 13 }} /> : <Check style={{ width: 13, height: 13 }} />}
              {isProcessing ? 'Generating...' : canvasConfirmed ? 'Generate FireRed Preview' : 'Confirm Component '}
            </button>
            <button onClick={handleReset} disabled={!transform} className="flex h-9 items-center gap-1.5 rounded-[5px] border border-[#E4E4E4] px-3 text-xs font-medium text-[#525252] hover:border-[#A3A3A3] disabled:cursor-not-allowed disabled:opacity-40">
              <RotateCcw style={{ width: 13, height: 13 }} /> Reset
            </button>
          </div>

          {generationLimitReached && <p className="mt-3 text-xs font-medium text-[#B45309]">Version 5 is the last editable base. Choose an earlier version to generate another preview.</p>}

          <div className="mt-5 space-y-2 border-t border-[#E4E4E4] pt-4">
            <div className="flex items-center justify-between">
              <p className="label-caps">Version Queue</p>
              <span className="text-[10px] font-medium text-[#9CA3AF]">{'1 -> 2 -> 3'}</span>
            </div>
            {versions.map(version => (
              <div
                key={version.version}
                className={cn(
                  'rounded-[6px] border bg-white p-2.5 text-xs transition-colors duration-[120ms]',
                  version.version === sourceVersion ? 'border-[#BFDBFE] bg-[#F8FBFF]' : 'border-[#E4E4E4]'
                )}
              >
                <div className="flex items-start gap-3">
                  <button
                    onClick={() => handleInspectVersion(version)}
                    className={cn(
                      'relative h-14 w-[72px] shrink-0 overflow-hidden rounded-[4px] border bg-[#0A0A0A] transition-colors duration-[120ms]',
                      inspectedVersion?.version === version.version ? 'border-[#1450F5]' : 'border-[#E4E4E4] hover:border-[#1450F5]'
                    )}
                    aria-label={`Preview Version ${version.version}`}
                    title={`Preview Version ${version.version}`}
                  >
                    <img src={version.url} alt="" className="h-full w-full object-cover" />
                    <span className="absolute inset-0 flex items-center justify-center bg-black/0 text-white opacity-0 transition-opacity duration-[120ms] hover:bg-black/35 hover:opacity-100">
                      <Eye style={{ width: 14, height: 14 }} />
                    </span>
                  </button>

                  <button onClick={() => handleInspectVersion(version)} className="min-w-0 flex-1 text-left hover:text-[#1450F5]">
                    <span className="flex flex-wrap items-center gap-1.5 font-semibold text-[#111827]">
                      Version {version.version}
                      {version.version === sourceVersion && <span className="rounded-full bg-[#DBEAFE] px-1.5 py-0.5 text-[9px] font-semibold text-[#1450F5]">Base</span>}
                    </span>
                    <span className="mt-1 block truncate text-[11px] text-[#9CA3AF]">{version.sourceVersion ? `Generated from Version ${version.sourceVersion}` : 'Preview step output'}</span>
                  </button>
                </div>

                <div className="mt-2 flex items-center justify-end gap-2 border-t border-[#EEF2F7] pt-2">
                  <button onClick={() => handleEditFromVersion(version)} className="rounded-[4px] px-2 py-1 text-[11px] font-semibold text-[#1450F5] hover:bg-[#EFF6FF]">Edit from</button>
                  <button onClick={() => handleUseVersion(version)} className="rounded-[4px] px-2 py-1 text-[11px] font-semibold text-[#525252] hover:bg-[#F5F5F5] hover:text-[#1450F5]">Use for video</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
