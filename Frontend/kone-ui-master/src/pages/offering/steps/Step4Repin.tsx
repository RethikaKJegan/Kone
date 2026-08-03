import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, ChevronDown, ChevronLeft, ChevronRight, Eraser, Eye, Redo2, RotateCcw, Undo2, Wand2 } from 'lucide-react'
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

function componentImageFor(offering: { selectedComponentAssets?: Partial<Record<ComponentKey, string>> } | null | undefined, component: ComponentKey) {
  return offering?.selectedComponentAssets?.[component] ?? COMP_IMAGES[component] ?? null
}
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


function eraserEntryFromTransform(transform: RepinTransform) {
  return {
    repinBackgroundUrl: transform.repinBackgroundUrl ?? null,
    repinBackgroundDisplayUrl: transform.repinBackgroundDisplayUrl ?? transform.repinBackgroundUrl ?? null,
  }
}

function hasManualEraserBackground(transform: RepinTransform | null | undefined) {
  return Boolean(transform?.eraserHistory && transform.eraserHistory.length > 1)
}

function repinBackgroundForEditing(transform: RepinTransform | null | undefined, allowGeneratedBackground = false) {
  return hasManualEraserBackground(transform) || allowGeneratedBackground
    ? transform?.repinBackgroundDisplayUrl ?? transform?.repinBackgroundUrl ?? null
    : null
}

function transformForRepinSubmit(transform: RepinTransform, allowGeneratedBackground = false): RepinTransform {
  if (hasManualEraserBackground(transform) || allowGeneratedBackground) return transform
  return {
    ...transform,
    repinBackgroundUrl: null,
    repinBackgroundDisplayUrl: null,
    repinBackgroundPath: null,
  }
}

function transformWithEraserEntry(transform: RepinTransform, entry: ReturnType<typeof eraserEntryFromTransform>, eraserHistory: ReturnType<typeof eraserEntryFromTransform>[], eraserRedoStack: ReturnType<typeof eraserEntryFromTransform>[] = []): RepinTransform {
  return {
    ...transform,
    repinBackgroundUrl: entry.repinBackgroundUrl,
    repinBackgroundDisplayUrl: entry.repinBackgroundDisplayUrl,
    eraserHistory,
    eraserRedoStack,
  }
}

function quadFromRect(transform: RepinTransform): RepinTransform['points'] {
  const x = Number(transform.x || 0)
  const y = Number(transform.y || 0)
  const width = Number(transform.width || 0)
  const height = Number(transform.height || 0)
  return [
    { x, y },
    { x: x + width, y },
    { x: x + width, y: y + height },
    { x, y: y + height },
  ]
}

function transformWithNumericField(transform: RepinTransform, field: keyof Pick<RepinTransform, 'x' | 'y' | 'width' | 'height' | 'rotation' | 'skewX' | 'skewY'>, value: number): RepinTransform {
  const next = { ...transform, [field]: value }
  if (field === 'x' || field === 'y' || field === 'width' || field === 'height') {
    return { ...next, points: quadFromRect(next) }
  }
  return next
}

function transformHistoryKey(component: ComponentKey, sourceVersion: number) {
  return `${component}:${sourceVersion}`
}

function transformSnapshot(transform: RepinTransform) {
  return JSON.stringify({
    x: transform.x,
    y: transform.y,
    width: transform.width,
    height: transform.height,
    rotation: transform.rotation || 0,
    skewX: transform.skewX || 0,
    skewY: transform.skewY || 0,
    points: transform.points ?? null,
    sourceVersion: transform.sourceVersion,
    targetVersion: transform.targetVersion,
    repinBackgroundUrl: transform.repinBackgroundUrl ?? null,
    repinBackgroundDisplayUrl: transform.repinBackgroundDisplayUrl ?? null,
  })
}

export default function Step4Repin() {
  const { projectId, offeringId } = useParams()
  const navigate = useNavigate()
  const { currentOffering, setCurrentOffering, setRepinTransforms, submitRepinPreview, eraseRepinBackground, goToStep, isProcessing } = useOfferingStore()
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
  const [repinTransforms, setLocalRepinTransforms] = useState<Partial<Record<ComponentKey, RepinTransform>>>(offering?.repinTransforms ?? {})
  const [transformHistory, setTransformHistory] = useState<Record<string, RepinTransform[]>>({})
  const [feedbackOptions, setFeedbackOptions] = useState<RepinFeedbackOption[]>(['seamless_blending'])
  const [inspectedVersion, setInspectedVersion] = useState<PreviewVersion | null>(null)
  const [canvasConfirmed, setCanvasConfirmed] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [eraserMode, setEraserMode] = useState(false)
  const [placementPreview, setPlacementPreview] = useState(false)
  const [sourceChooserComp, setSourceChooserComp] = useState<ComponentKey | null>(null)
  const [eraserBrushSize, setEraserBrushSize] = useState(48)

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
    setEraserMode(false)
    setPlacementPreview(false)
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
  const sourceBaseMode: 'original' | 'version' = 'version'
  const defaultTransformFor = (component: ComponentKey) => repinTransformFromPin(component, sourceVersion, targetVersion, pins.find((p: ComponentPin) => p.componentKey === component))

  const selectedComponentImageUrl = selectedComp ? componentImageFor(offering, selectedComp) : null
  const transform = selectedComp ? repinTransforms[selectedComp] ?? defaultTransformFor(selectedComp) : null
  const selectedHistoryKey = selectedComp ? transformHistoryKey(selectedComp, sourceVersion) : null
  const canUndoGeometry = Boolean(selectedHistoryKey && transformHistory[selectedHistoryKey]?.length)
  const canUndoEraser = Boolean(transform?.eraserHistory && transform.eraserHistory.length > 1)
  const canRedoEraser = Boolean(transform?.eraserRedoStack && transform.eraserRedoStack.length > 0)
  const isSameComponentReEdit = Boolean(selectedComp && sourceVersion > 1 && sourceVersionComponent === selectedComp)
  const canvasBaseBackgroundUrl = sourceVersion > 1 || selectedComp === 'door' ? (previewImageUrl ?? originalImageUrl) : (originalImageUrl ?? previewImageUrl)
  const hasGeneratedRepinBackground = sourceVersion > 1
  const sameComponentSourcePreview = isSameComponentReEdit && selectedSourcePreview?.sourceVersion
    ? versions.find(item => Number(item.version) === Number(selectedSourcePreview.sourceVersion))
    : null
  const sameComponentSourceBackgroundUrl = sameComponentSourcePreview
    ? versionUrl(sameComponentSourcePreview, originalImageUrl)
    : null
  const manualEraserBackgroundUrl = hasManualEraserBackground(transform)
    ? transform?.repinBackgroundDisplayUrl ?? transform?.repinBackgroundUrl ?? null
    : null
  const editingBackgroundUrl = manualEraserBackgroundUrl ?? (isSameComponentReEdit
    ? (sameComponentSourceBackgroundUrl ?? repinBackgroundForEditing(transform, true) ?? canvasBaseBackgroundUrl)
    : sourceVersion > 1 || selectedComp === 'door'
      ? canvasBaseBackgroundUrl
      : (repinBackgroundForEditing(transform, hasGeneratedRepinBackground) ?? canvasBaseBackgroundUrl))
  const eraserBackgroundRevision = [
    transform?.eraserHistory?.length ?? 0,
    transform?.repinBackgroundDisplayUrl ?? transform?.repinBackgroundUrl ?? '',
  ].join(':')
  const editingCanvasImageUrl = useMemo(() => {
    if (!editingBackgroundUrl) return null
    if (!hasManualEraserBackground(transform)) return editingBackgroundUrl
    const separator = editingBackgroundUrl.includes('?') ? '&' : '?'
    return editingBackgroundUrl + separator + 'magicEraserRevision=' + encodeURIComponent(eraserBackgroundRevision)
  }, [editingBackgroundUrl, eraserBackgroundRevision, transform?.eraserHistory])
  const generatedComponentsInSource = new Set(
    versions
      .filter(version => version.version <= sourceVersion)
      .map(version => version.transform?.componentKey)
      .filter(Boolean) as ComponentKey[]
  )
  const staticComponentLayers = false
    ? components
        .filter(comp => comp !== selectedComp && !generatedComponentsInSource.has(comp))
        .map(comp => {
          const layerTransform = repinTransforms[comp] ?? defaultTransformFor(comp)
          return {
            transform: layerTransform,
            label: COMP_LABELS[comp],
            componentImageUrl: componentImageFor(offering, comp) ?? layerTransform.editableLayerUrl ?? null,
          }
        })
        .filter(layer => Boolean(layer.componentImageUrl))
    : []

  const persistTransforms = (nextTransforms: Partial<Record<ComponentKey, RepinTransform>>) => {
    setLocalRepinTransforms(nextTransforms)
    setRepinTransforms(nextTransforms)
  }

  const rememberTransform = (snapshot: RepinTransform) => {
    const key = transformHistoryKey(snapshot.componentKey, snapshot.sourceVersion)
    setTransformHistory(prev => {
      const history = prev[key] ?? []
      if (history.length && transformSnapshot(history[history.length - 1]) === transformSnapshot(snapshot)) return prev
      return { ...prev, [key]: [...history, snapshot] }
    })
  }

  const handleSelectComponent = (component: ComponentKey) => {
    if (versions.length > 1) {
      const shouldOpenChooser = sourceChooserComp !== component
      if (selectedComp !== component) {
        handleStartComponent(component, latestVersion || sourceVersion)
      }
      setSourceChooserComp(shouldOpenChooser ? component : null)
      return
    }
    handleStartComponent(component, sourceVersion)
  }

  const handleStartComponent = (component: ComponentKey, version: number) => {
    const nextTargetVersion = Math.min(latestVersion + 1, 5)
    const existing = repinTransforms[component]
    const versionPreview = versions.find(item => item.version === version)
    const sameComponentReEdit = version > 1 && versionPreview?.transform?.componentKey === component
    const pinTransform = repinTransformFromPin(component, version, nextTargetVersion, pins.find((p: ComponentPin) => p.componentKey === component))
    const seedTransform = sameComponentReEdit ? (versionPreview?.transform ?? existing ?? pinTransform) : (existing ?? pinTransform)
    const sameComponentEditableLayerUrl = sameComponentReEdit
      ? versionPreview?.transform?.editableLayerUrl ?? existing?.editableLayerUrl ?? null
      : seedTransform.editableLayerUrl ?? null
    const sourceOfVersionPreview = versionPreview?.sourceVersion
      ? versions.find(item => Number(item.version) === Number(versionPreview.sourceVersion))
      : null
    const sameComponentSourceBackgroundUrl = sameComponentReEdit
      ? versionUrl(sourceOfVersionPreview ?? undefined, originalImageUrl)
      : null
    const backgroundTransform = sameComponentReEdit
      ? ([versionPreview?.transform, existing, pinTransform].find(item => item?.repinBackgroundUrl) ?? versionPreview?.transform ?? existing ?? pinTransform)
      : null
    const sameComponentBackgroundUrl = sameComponentReEdit
      ? sameComponentSourceBackgroundUrl
        ?? backgroundTransform?.repinBackgroundUrl
        ?? backgroundTransform?.repinBackgroundDisplayUrl
        ?? null
      : null
    const sameComponentBackgroundDisplayUrl = sameComponentReEdit
      ? sameComponentSourceBackgroundUrl
        ?? backgroundTransform?.repinBackgroundDisplayUrl
        ?? backgroundTransform?.repinBackgroundUrl
        ?? null
      : null
    const nextTransform = {
      ...seedTransform,
      componentKey: component,
      componentType: component,
      sourceVersion: version,
      targetVersion: nextTargetVersion,
      editableLayerUrl: sameComponentEditableLayerUrl,
      repinBackgroundUrl: sameComponentBackgroundUrl,
      repinBackgroundDisplayUrl: sameComponentBackgroundDisplayUrl,
      eraserHistory: backgroundTransform?.eraserHistory ?? [],
      eraserRedoStack: backgroundTransform?.eraserRedoStack ?? [],
    }
    setSelectedSourceVersion(version)
    setSelectedComp(component)
    setSourceChooserComp(null)
    setInspectedVersion(null)
    setCanvasConfirmed(false)
    setEraserMode(false)
    setPlacementPreview(false)
    persistTransforms({ ...repinTransforms, [component]: nextTransform })
  }

  const handleTransformEditStart = (snapshot: RepinTransform) => {
    rememberTransform(snapshot)
  }

  const handleTransformChange = (next: RepinTransform) => {
    const current = repinTransforms[next.componentKey]
    if (current && transformSnapshot(current) !== transformSnapshot(next)) {
      rememberTransform(current)
    }
    setPlacementPreview(false)
    setCanvasConfirmed(false)
    // Keep intermediate canvas movements local so dragging remains smooth
    // without sending an API request for every pointer movement.
    setLocalRepinTransforms({
      ...repinTransforms,
      [next.componentKey]: next,
    })
  }


  const handleEraseMask = async (maskDataUrl: string) => {
    if (!transform || !selectedComp || isProcessing) return
    try {
      const activeTransform = { ...transform, componentKey: selectedComp, componentType: selectedComp }
      const nextTransform = await eraseRepinBackground(activeTransform, maskDataUrl, sourceVersion, sourceBaseMode)
      const selectedTransform = { ...nextTransform, componentKey: selectedComp, componentType: selectedComp }
      const latestTransforms = useOfferingStore.getState().currentOffering?.repinTransforms ?? repinTransforms
      persistTransforms({ ...latestTransforms, [selectedComp]: selectedTransform })
      setCanvasConfirmed(false)
      setEraserMode(false)
      setPlacementPreview(false)
      toast('Magic Eraser cleaned the selected area')
    } catch (error) {
      toast(error instanceof Error ? error.message : 'Magic Eraser failed', 'destructive')
    }
  }


  const handleUndoEraser = () => {
    if (!transform || !selectedComp || !canUndoEraser) return
    const history = transform.eraserHistory ?? []
    const currentEntry = history[history.length - 1]
    const previousEntry = history[history.length - 2]
    const nextTransform = transformWithEraserEntry(
      transform,
      previousEntry,
      history.slice(0, -1),
      [currentEntry, ...(transform.eraserRedoStack ?? [])]
    )
    persistTransforms({ ...repinTransforms, [selectedComp]: nextTransform })
    setCanvasConfirmed(false)
  }

  const handleRedoEraser = () => {
    if (!transform || !selectedComp || !canRedoEraser) return
    const [redoEntry, ...remainingRedo] = transform.eraserRedoStack ?? []
    const history = transform.eraserHistory?.length ? transform.eraserHistory : [eraserEntryFromTransform(transform)]
    const nextTransform = transformWithEraserEntry(
      transform,
      redoEntry,
      [...history, redoEntry],
      remainingRedo
    )
    persistTransforms({ ...repinTransforms, [selectedComp]: nextTransform })
    setCanvasConfirmed(false)
  }

  const handleNumericChange = (field: keyof Pick<RepinTransform, 'x' | 'y' | 'width' | 'height' | 'rotation' | 'skewX' | 'skewY'>, value: number) => {
    if (!transform || !selectedComp) return
    rememberTransform(transform)
    setCanvasConfirmed(false)
    setPlacementPreview(false)
    persistTransforms({ ...repinTransforms, [selectedComp]: transformWithNumericField(transform, field, value) })
  }

  const handleReset = () => {
    if (!selectedComp || !selectedHistoryKey) return
    const history = transformHistory[selectedHistoryKey] ?? []
    const previousTransform = history[history.length - 1]
    if (!previousTransform) return
    setTransformHistory(prev => ({ ...prev, [selectedHistoryKey]: history.slice(0, -1) }))
    setCanvasConfirmed(false)
    setPlacementPreview(false)
    persistTransforms({ ...repinTransforms, [selectedComp]: previousTransform })
  }

  const handleConfirmCanvas = () => {
    if (!selectedComp || !transform) return

    // Persist only the final confirmed transform.
    persistTransforms({
      ...repinTransforms,
      [selectedComp]: transform,
    })

    setInspectedVersion(null)
    setPlacementPreview(false)
    setCanvasConfirmed(true)
  }

  const handleInspectVersion = (version: PreviewVersion) => {
    setSourceChooserComp(null)
    setInspectedVersion(version)
  }

  const inspectedVersionIndex = inspectedVersion
    ? versions.findIndex(version => version.version === inspectedVersion.version)
    : -1
  const previousInspectedVersion = inspectedVersionIndex > 0 ? versions[inspectedVersionIndex - 1] : null
  const nextInspectedVersion = inspectedVersionIndex >= 0 && inspectedVersionIndex < versions.length - 1 ? versions[inspectedVersionIndex + 1] : null

  const persistFeedbackOptions = (nextOptions: RepinFeedbackOption[]) => {
    setFeedbackOptions(nextOptions)
    if (!selectedComp || !transform) return
    persistTransforms({
      ...repinTransforms,
      [selectedComp]: { ...transform, feedbackOption: nextOptions[0] ?? null, feedbackOptions: nextOptions },
    })
  }

  const handleFeedbackChange = (option: RepinFeedbackOption) => {
    const nextOptions = feedbackOptions.includes(option)
      ? feedbackOptions.filter(item => item !== option)
      : [...feedbackOptions, option]
    persistFeedbackOptions(nextOptions)
  }

  const handleNoFeedback = () => {
    persistFeedbackOptions([])
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
    const payload = {
      ...transformForRepinSubmit(transform, hasGeneratedRepinBackground || isSameComponentReEdit),
      componentKey: selectedComp,
      componentType: selectedComp,
      sourceVersion,
      targetVersion,
      rotation: transform.rotation || 0,
      skewX: transform.skewX || 0,
      skewY: transform.skewY || 0,
      editableLayerUrl: isSameComponentReEdit ? transform.editableLayerUrl ?? null : null,
      repinBackgroundUrl: transform.repinBackgroundUrl ?? null,
      repinBackgroundDisplayUrl: transform.repinBackgroundDisplayUrl ?? null,
      feedbackOption: feedbackOptions[0] ?? null,
      feedbackOptions,
      sourceBaseMode,
      sourceVersionComponent,
    }
    try {
      await submitRepinPreview(payload)
      toast('Generating repin preview ')
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
          <p className="mt-1 text-[12px] text-[#9CA3AF]">Adjust component geometry, then generate a realistic preview.</p>
        </div>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
      </div>

      <div className="mt-4 flex gap-0 border-t border-[#E9ECEF]">
        <div className="relative flex-[3] p-6 pr-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap gap-2">
              {components.map(comp => (
                <div key={comp} className="relative">
                  <button
                    type="button"
                    onClick={() => handleSelectComponent(comp)}
                    className={cn(
                      "min-w-[128px] rounded-[5px] border px-3 py-2 text-left text-xs font-medium transition-colors duration-[120ms]",
                      selectedComp === comp ? "border-[#1450F5] bg-[#EFF6FF] text-[#1450F5]" : "border-[#E4E4E4] text-[#525252] hover:border-[#BFDBFE]"
                    )}
                  >
                    <span className="block truncate">{COMP_LABELS[comp]}</span>
                    <span className="mt-1 block text-[10px] font-medium text-[#9CA3AF]">
                      {selectedComp === comp ? "From Version " + sourceVersion : "Choose base"}
                    </span>
                  </button>
                  {sourceChooserComp === comp && (
                    <div className="absolute left-0 top-[calc(100%+6px)] z-30 w-48 rounded-[6px] border border-[#DADDE3] bg-white p-2 shadow-lg">
                      <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[#9CA3AF]">Start from</p>
                      {versions.map(version => (
                        <button
                          key={version.version}
                          type="button"
                          onClick={() => handleStartComponent(comp, version.version)}
                          className="flex w-full items-center justify-between rounded-[4px] px-2 py-1.5 text-left text-[11px] font-semibold text-[#525252] hover:bg-[#EFF6FF] hover:text-[#1450F5]"
                        >
                          <span>{version.version === latestVersion ? "Latest approved" : "Version " + version.version}</span>
                          <span className="text-[10px] font-medium text-[#9CA3AF]">V{version.version}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
            <span className="text-[11px] font-medium text-[#9CA3AF]">Editing Version {sourceVersion} to {targetVersion}</span>
          </div>

          {transform && selectedComp ? (
            inspectedVersion ? (
              <div className="relative flex min-h-[360px] items-center justify-center overflow-hidden rounded-lg border border-[#E4E4E4] bg-[#0A0A0A]">
                <img src={inspectedVersion.url} alt={"Version " + inspectedVersion.version} className="max-h-[520px] w-full object-contain" />
                <div className="absolute left-3 top-3 rounded-[4px] bg-black/70 px-2 py-1 text-[11px] font-semibold text-white">Version {inspectedVersion.version}</div>
                <div className="absolute right-3 top-3">
                  <button onClick={() => setInspectedVersion(null)} className="rounded-[4px] bg-white px-2 py-1 text-[11px] font-semibold text-[#111827] shadow-sm hover:text-[#1450F5]">Back to editing</button>
                </div>
                {previousInspectedVersion && (
                  <button
                    type="button"
                    onClick={() => setInspectedVersion(previousInspectedVersion)}
                    className="absolute left-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-[#111827] shadow-sm transition-colors duration-[120ms] hover:bg-white hover:text-[#1450F5]"
                    aria-label={"Preview Version " + previousInspectedVersion.version}
                    title={"Version " + previousInspectedVersion.version}
                  >
                    <ChevronLeft style={{ width: 18, height: 18 }} />
                  </button>
                )}
                {nextInspectedVersion && (
                  <button
                    type="button"
                    onClick={() => setInspectedVersion(nextInspectedVersion)}
                    className="absolute right-3 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-white/90 text-[#111827] shadow-sm transition-colors duration-[120ms] hover:bg-white hover:text-[#1450F5]"
                    aria-label={"Preview Version " + nextInspectedVersion.version}
                    title={"Version " + nextInspectedVersion.version}
                  >
                    <ChevronRight style={{ width: 18, height: 18 }} />
                  </button>
                )}
              </div>
            ) : (
              <RepinTransformCanvas
                key={String(selectedComp) + ":" + String(sourceVersion) + ":" + eraserBackgroundRevision + ":" + (isSameComponentReEdit ? (transform.editableLayerUrl ?? 'generated-layer') : (selectedComponentImageUrl ?? 'asset'))}
                imageUrl={editingCanvasImageUrl}
                transform={transform}
                label={COMP_LABELS[selectedComp]}
                componentImageUrl={isSameComponentReEdit ? (transform.editableLayerUrl ?? null) : (selectedComponentImageUrl ?? transform.editableLayerUrl ?? null)}
                staticLayers={staticComponentLayers}
                eraserEnabled={eraserMode && !placementPreview}
                eraserBrushSize={eraserBrushSize}
                previewOnly={placementPreview}
                onErase={handleEraseMask}
                onEditStart={handleTransformEditStart}
                onChange={handleTransformChange}
              />
            )
          ) : (
            <div className="flex min-h-[360px] items-center justify-center rounded-lg border border-[#E4E4E4] text-sm text-[#6B7280]">Select a component to repin.</div>
          )}
          {transform && selectedComp && !canvasConfirmed && !inspectedVersion && (
            <p className="mt-3 text-xs text-[#6B7280]">{eraserMode ? 'Paint over the object to erase. Release to run Magic Eraser cleanup.' : 'Drag the component or any single corner, then confirm placement before generating the preview.'}</p>
          )}
        </div>

        <div className="flex flex-[2] flex-col border-l border-[#E9ECEF] p-6 pl-4">
          <div className="mb-4 flex items-center justify-between">
            <p className="label-caps">Current Task</p>
            <span className={cn('rounded-full px-2 py-1 text-[10px] font-semibold', canvasConfirmed ? 'bg-[#ECFDF5] text-[#047857]' : 'bg-[#FEF3C7] text-[#92400E]')}>
              {canvasConfirmed ? 'Placement confirmed' : 'Needs confirmation'}
            </span>
          </div>

          <div className="rounded-[6px] border border-[#E4E4E4] bg-[#FAFAFA] p-3">
            <p className="text-xs font-semibold text-[#111827]">{selectedComp ? COMP_LABELS[selectedComp] : 'Component'}</p>
            <p className="mt-1 text-[11px] leading-4 text-[#6B7280]">
              Move the overlay or drag any corner independently to fit the camera perspective.
            </p>
          </div>

          <div className="mt-4 rounded-[6px] border border-[#E4E4E4] bg-white p-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setPlacementPreview(false)
                    setEraserMode(value => !value)
                  }}
                  disabled={!transform || isProcessing}
                  className={cn(
                    'flex h-8 items-center gap-1.5 rounded-[5px] border px-3 text-xs font-medium transition-colors duration-[120ms] disabled:cursor-not-allowed disabled:opacity-40',
                    eraserMode ? 'border-[#1450F5] bg-[#EFF6FF] text-[#1450F5]' : 'border-[#E4E4E4] text-[#525252] hover:border-[#BFDBFE]'
                  )}
                >
                  <Eraser style={{ width: 13, height: 13 }} /> Magic Eraser
                </button>
                <button
                  type="button"
                  onClick={handleUndoEraser}
                  disabled={!canUndoEraser || isProcessing}
                  className="flex h-8 w-8 items-center justify-center rounded-[5px] border border-[#E4E4E4] text-[#525252] transition-colors duration-[120ms] hover:border-[#BFDBFE] hover:text-[#1450F5] disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Undo Magic Eraser"
                  title="Undo Magic Eraser"
                >
                  <Undo2 style={{ width: 14, height: 14 }} />
                </button>
                <button
                  type="button"
                  onClick={handleRedoEraser}
                  disabled={!canRedoEraser || isProcessing}
                  className="flex h-8 w-8 items-center justify-center rounded-[5px] border border-[#E4E4E4] text-[#525252] transition-colors duration-[120ms] hover:border-[#BFDBFE] hover:text-[#1450F5] disabled:cursor-not-allowed disabled:opacity-40"
                  aria-label="Redo Magic Eraser"
                  title="Redo Magic Eraser"
                >
                  <Redo2 style={{ width: 14, height: 14 }} />
                </button>
              </div>
              {eraserMode && (
                <div className="flex h-12 w-16 items-center justify-center" aria-label="Brush size preview">
                  <span
                    className="block rounded-full border border-[#1450F5] bg-[rgba(20,80,245,0.28)] shadow-[0_0_0_1px_rgba(20,80,245,0.12)]"
                    style={{ width: Math.max(8, eraserBrushSize / 4), height: Math.max(8, eraserBrushSize / 4) }}
                  />
                </div>
              )}
            </div>
            {eraserMode && (
              <label className="mt-3 block text-[11px] font-medium text-[#6B7280]">
                Brush size
                <input
                  type="range"
                  min={12}
                  max={240}
                  step={4}
                  value={eraserBrushSize}
                  onChange={event => setEraserBrushSize(Number(event.target.value))}
                  className="mt-2 w-full accent-[#1450F5]"
                />
              </label>
            )}
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
              <label className="flex items-center gap-2 text-xs font-semibold text-[#525252]">
                <input type="checkbox" checked={feedbackOptions.length === 0} onChange={handleNoFeedback} />
                No feedback
              </label>
              {FEEDBACK_OPTIONS.map(option => (
                <label key={option.value} className="flex items-center gap-2 text-xs text-[#525252]">
                  <input type="checkbox" checked={feedbackOptions.includes(option.value)} onChange={() => handleFeedbackChange(option.value)} />
                  {option.label}
                </label>
              ))}
            </fieldset>
          )}

          <div className="mt-5 space-y-2">
            <button
              onClick={handlePrimaryAction}
              disabled={isProcessing || generationLimitReached || !transform}
              className={cn(
                'flex h-10 w-full items-center justify-center gap-1.5 rounded-[5px] px-4 text-xs font-semibold text-white transition-colors duration-[120ms] disabled:cursor-not-allowed disabled:opacity-40',
                canvasConfirmed ? 'bg-[#0A0A0A] hover:bg-[#262626]' : 'bg-[#1450F5] hover:bg-[#0B3BBF]'
              )}
            >
              {canvasConfirmed ? <Wand2 style={{ width: 13, height: 13 }} /> : <Check style={{ width: 13, height: 13 }} />}
              {isProcessing ? 'Generating Version...' : canvasConfirmed ? 'Generate Version' : 'Confirm Position'}
            </button>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => {
                  setEraserMode(false)
                  setPlacementPreview(value => !value)
                }}
                disabled={!transform || isProcessing || Boolean(inspectedVersion)}
                className="flex h-8 items-center justify-center gap-1.5 rounded-[5px] text-xs font-semibold text-[#525252] transition-colors duration-[120ms] hover:bg-[#F5F7FA] hover:text-[#1450F5] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Eye style={{ width: 13, height: 13 }} /> {placementPreview ? 'Resume editing' : 'Position check'}
              </button>
              <button
                type="button"
                onClick={handleReset}
                disabled={!canUndoGeometry || isProcessing}
                className="flex h-8 items-center justify-center gap-1.5 rounded-[5px] text-xs font-semibold text-[#525252] transition-colors duration-[120ms] hover:bg-[#F5F7FA] hover:text-[#1450F5] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <RotateCcw style={{ width: 13, height: 13 }} /> Undo position
              </button>
            </div>
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

                <div className="mt-2 flex items-center justify-end border-t border-[#EEF2F7] pt-2">
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