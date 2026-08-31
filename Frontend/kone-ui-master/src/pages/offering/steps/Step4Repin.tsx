import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Check, ChevronDown, ChevronLeft, ChevronRight, Eraser, Eye, Redo2, RotateCcw, Undo2, Wand2 } from 'lucide-react'
import apiClient from '../../../api/client'
import { getGuestSessionId, isGuestSession } from '../../../api/guestWorkflow'
import { useOfferingStore } from '../../../store/offeringStore'
import { RepinTransformCanvas, repinTransformFromPin } from '../../../components/shared/RepinTransformCanvas'
import { KONE_COMPONENTS, componentDefaultAsset, componentDisplayLabel, semanticComponentKey } from '../../../lib/constants'
import { toast } from '../../../hooks/useToast'
import { safeSystemErrorMessage } from '../../../lib/safeErrors'
import { cn } from '../../../lib/utils'
import type { ComponentKey, ComponentPin, EraserHistoryEntry, PreviewVersion, RepinFeedbackOption, RepinSharedBackgroundState, RepinTransform, SemanticComponentKey } from '../../../types'

function componentImageFor(offering: { selectedComponentAssets?: Partial<Record<ComponentKey, string>> } | null | undefined, component: ComponentKey) {
  return offering?.selectedComponentAssets?.[component] ?? componentDefaultAsset(component)
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


function eraserEntryFromSharedBackground(sharedState: RepinSharedBackgroundState | null | undefined): EraserHistoryEntry {
  return {
    repinBackgroundUrl: sharedState?.repinBackgroundUrl ?? null,
    repinBackgroundDisplayUrl: sharedState?.repinBackgroundDisplayUrl ?? sharedState?.repinBackgroundUrl ?? null,
  }
}

function hasManualEraserBackground(sharedState: RepinSharedBackgroundState | null | undefined) {
  return Boolean(
    (sharedState?.eraserHistory && sharedState.eraserHistory.length > 1) ||
    sharedState?.repinBackgroundUrl
  )
}

function sharedBackgroundWithEraserEntry(
  entry: EraserHistoryEntry,
  eraserHistory: EraserHistoryEntry[],
  eraserRedoStack: EraserHistoryEntry[] = []
): RepinSharedBackgroundState {
  return {
    repinBackgroundUrl: entry.repinBackgroundUrl,
    repinBackgroundDisplayUrl: entry.repinBackgroundDisplayUrl ?? entry.repinBackgroundUrl ?? null,
    eraserHistory,
    eraserRedoStack,
  }
}

function transformForRepinSubmit(transform: RepinTransform, sharedState: RepinSharedBackgroundState | null | undefined, allowGeneratedBackground = false): RepinTransform {
  if (hasManualEraserBackground(sharedState)) {
    return {
      ...transform,
      repinBackgroundUrl: sharedState?.repinBackgroundUrl ?? null,
      repinBackgroundDisplayUrl: sharedState?.repinBackgroundDisplayUrl ?? sharedState?.repinBackgroundUrl ?? null,
      repinBackgroundPath: null,
      eraserHistory: sharedState?.eraserHistory ?? [],
      eraserRedoStack: sharedState?.eraserRedoStack ?? [],
      magicEraserApplied: true,
    }
  }
  if (allowGeneratedBackground) return transform
  return {
    ...transform,
    repinBackgroundUrl: null,
    repinBackgroundDisplayUrl: null,
    repinBackgroundPath: null,
    eraserHistory: [],
    eraserRedoStack: [],
    magicEraserApplied: false,
  }
}

function transformWithoutSharedEraserState(transform: RepinTransform, sharedState: RepinSharedBackgroundState | null | undefined): RepinTransform {
  if (!hasManualEraserBackground(sharedState)) return transform
  return {
    ...transform,
    repinBackgroundUrl: null,
    repinBackgroundDisplayUrl: null,
    repinBackgroundPath: null,
    eraserHistory: [],
    eraserRedoStack: [],
    magicEraserApplied: false,
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

function transformHistoryKey(component: string, sourceVersion: number) {
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
  const { currentOffering, setCurrentOffering, setRepinTransforms, setRepinSharedBackgrounds, submitRepinPreview, eraseRepinBackground, goToStep, isProcessing } = useOfferingStore()
  const offering = currentOffering
  const selectedComponents = offering?.selectedComponents ?? []
  const componentRefs: { id: ComponentKey; type: SemanticComponentKey }[] = selectedComponents.length
    ? selectedComponents.map(component => ({ id: component, type: semanticComponentKey(component) }))
    : KONE_COMPONENTS.map(component => ({ id: component.key, type: semanticComponentKey(component.key) }))
  const components = componentRefs.map(ref => ref.id)
  const componentTypeFor = (componentId: string): SemanticComponentKey => componentRefs.find(ref => ref.id === componentId)?.type ?? semanticComponentKey(componentId as ComponentKey)
  const componentInstanceFor = (componentId: string) => offering?.componentInstances?.find(instance => instance.id === componentId)
  const componentLabelFor = (componentId: string) => componentDisplayLabel(componentId as ComponentKey, componentInstanceFor(componentId)?.assetUrl ?? offering?.selectedComponentAssets?.[componentId as ComponentKey])
  const componentImageForId = (componentId: string) => componentInstanceFor(componentId)?.assetUrl ?? componentImageFor(offering, componentId as ComponentKey)
  const pins = offering?.componentPins ?? []
  const pinsSignature = useMemo(() => pins.map(pin => [
    pin.componentKey,
    pin.x,
    pin.y,
    pin.imageWidth ?? '',
    pin.imageHeight ?? '',
    (pin.bbox ?? []).join(','),
  ].join(':')).join('|'), [pins])
  const versions = offering?.previewVersions?.length
    ? offering.previewVersions
    : offering?.outputImageUrl
      ? [{ version: 1, url: offering.outputImageUrl }]
      : []
  const latestVersion = versions.reduce((max, version) => Math.max(max, version.version), versions.length ? 1 : 0)
  const repinStateKey = offering?.id ? 'kone-repin-state:' + offering.id : null
  const savedRepinState = (() => {
    if (!repinStateKey || typeof window === 'undefined') return null
    try { return JSON.parse(window.localStorage.getItem(repinStateKey) || 'null') } catch { return null }
  })() as { sourceVersion?: number; selectedComp?: ComponentKey } | null
  const [selectedSourceVersion, setSelectedSourceVersion] = useState(savedRepinState?.sourceVersion || latestVersion || 1)
  const sourceVersion = versions.some(version => version.version === selectedSourceVersion) ? selectedSourceVersion : latestVersion || 1
  const targetVersion = Math.min(latestVersion + 1, 5)
  const generationLimitReached = latestVersion >= 5
  const selectedSourcePreview = versions.find(v => v.version === sourceVersion)
  const repinHydrationContextKey = useMemo(() => [
    offering?.id ?? '',
    sourceVersion,
    targetVersion,
    components.join('|'),
    pinsSignature,
    selectedSourcePreview?.version ?? 'none',
  ].join('::'), [offering?.id, sourceVersion, targetVersion, components.join('|'), pinsSignature, selectedSourcePreview?.version])
  const savedSelectedComp = savedRepinState?.selectedComp && components.includes(savedRepinState.selectedComp) ? savedRepinState.selectedComp : null
  const [selectedComp, setSelectedComp] = useState<ComponentKey | null>(savedSelectedComp ?? components[0] ?? null)
  const [repinTransforms, setLocalRepinTransforms] = useState<Partial<Record<string, RepinTransform>>>(offering?.repinTransforms ?? {})
  const lastHydratedContextRef = useRef<string | null>(null)
  const [transformHistory, setTransformHistory] = useState<Record<string, RepinTransform[]>>({})
  const [feedbackOptions, setFeedbackOptions] = useState<RepinFeedbackOption[]>(['seamless_blending'])
  const [inspectedVersion, setInspectedVersion] = useState<PreviewVersion | null>(null)
  const [canvasConfirmed, setCanvasConfirmed] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [eraserMode, setEraserMode] = useState(false)
  const [placementPreview, setPlacementPreview] = useState(false)
  const [eraserBrushSize, setEraserBrushSize] = useState(48)
  const [generationStartedAt, setGenerationStartedAt] = useState<number | null>(null)
  const [generationElapsedSeconds, setGenerationElapsedSeconds] = useState(0)

  useEffect(() => {
    if (!repinStateKey || typeof window === 'undefined') return
    window.localStorage.setItem(repinStateKey, JSON.stringify({ sourceVersion, selectedComp }))
  }, [repinStateKey, sourceVersion, selectedComp])

  const sourceVersionTransforms = useMemo(() => {
    const exactKeyFor = (item: RepinTransform | null | undefined) => String(item?.componentId ?? item?.componentKey ?? '').toLowerCase()
    const versionTransformMap = new Map<string, RepinTransform>()
    ;(selectedSourcePreview?.transforms ?? []).forEach(item => {
      const exactKey = exactKeyFor(item)
      if (exactKey) versionTransformMap.set(exactKey, item)
    })
    const compatibilityTransform = selectedSourcePreview?.transform
    const compatibilityKey = exactKeyFor(compatibilityTransform)
    if (compatibilityTransform && compatibilityKey && !versionTransformMap.has(compatibilityKey)) {
      versionTransformMap.set(compatibilityKey, compatibilityTransform)
    }

    const nextTransforms: Partial<Record<string, RepinTransform>> = {}
    components.forEach(comp => {
      const componentType = componentTypeFor(comp)
      const fallbackTransform = offering?.repinTransforms?.[comp]
      const resolved = versionTransformMap.get(String(comp).toLowerCase())
        ?? fallbackTransform
        ?? repinTransformFromPin(comp as ComponentKey, sourceVersion, targetVersion, pins.find((p: ComponentPin) => p.componentKey === comp))
      nextTransforms[comp] = {
        ...resolved,
        componentId: comp,
        componentKey: comp as ComponentKey,
        componentType,
        sourceVersion,
        targetVersion,
      }
    })
    return nextTransforms
  }, [selectedSourcePreview, offering?.id, sourceVersion, targetVersion, components.join('|'), pinsSignature])

  useEffect(() => {
    if (!latestVersion) return
    setSelectedSourceVersion(current => versions.some(version => version.version === current) ? current : latestVersion)
  }, [latestVersion, versions.map(version => version.version).join('|')])

  useEffect(() => {
    const component = selectedComp && components.includes(selectedComp) ? selectedComp : components[0]
    if (component && selectedComp !== component) setSelectedComp(component)
  }, [selectedComp, components.join('|')])

  useEffect(() => {
    if (lastHydratedContextRef.current === repinHydrationContextKey) return
    setLocalRepinTransforms(sourceVersionTransforms)
    lastHydratedContextRef.current = repinHydrationContextKey
  }, [repinHydrationContextKey, sourceVersionTransforms])

  useEffect(() => {
    setCanvasConfirmed(false)
    setEraserMode(false)
    setPlacementPreview(false)
  }, [sourceVersion])

  useEffect(() => {
    if (!isProcessing || offering?.pipelineStatus !== 'processing') {
      setGenerationStartedAt(null)
      setGenerationElapsedSeconds(0)
      return
    }

    const startedAt = generationStartedAt ?? Date.now()
    if (!generationStartedAt) setGenerationStartedAt(startedAt)
    setGenerationElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
    const timer = window.setInterval(() => {
      setGenerationElapsedSeconds(Math.max(0, Math.floor((Date.now() - startedAt) / 1000)))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [isProcessing, offering?.pipelineStatus, generationStartedAt])

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
              componentPins: offering.componentPins,
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
            setCurrentOffering({ ...offering, pipelineStatus: 'failed', renderComplete: false, lastError: safeSystemErrorMessage() })
            toast(safeSystemErrorMessage(), 'destructive')
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
  }, [projectId, offeringId, offering?.previewRequestKey, offering?.pipelineStatus])

  const previewImageUrl = useMemo(() => versionUrl(selectedSourcePreview, offering?.outputImageUrl), [selectedSourcePreview, offering?.outputImageUrl])
  const parentFinalImagePath = selectedSourcePreview?.finalImagePath ?? selectedSourcePreview?.url ?? previewImageUrl ?? null
  const originalImageUrl = offering?.uploadedFileUrl ?? offering?.inputImagePath ?? null
  const sourceVersionComponent = selectedSourcePreview?.transform?.componentKey ?? null
  const sourceVersionComponentId = selectedSourcePreview?.transform?.componentId ?? null
  const sourceBaseMode: 'original' | 'version' = 'original'
  const defaultTransformFor = (componentId: string) => {
    const componentType = componentTypeFor(componentId)
    return { ...repinTransformFromPin(componentId as ComponentKey, sourceVersion, targetVersion, pins.find((p: ComponentPin) => p.componentKey === componentId)), componentId, componentKey: componentId as ComponentKey, componentType }
  }

  const selectedComponentType = selectedComp ? componentTypeFor(selectedComp) : null
  const selectedComponentImageUrl = selectedComp ? componentImageForId(selectedComp) : null
  const transform = selectedComp ? repinTransforms[selectedComp] ?? defaultTransformFor(selectedComp) : null
  const selectedHistoryKey = selectedComp ? transformHistoryKey(selectedComp, sourceVersion) : null
  const canUndoGeometry = Boolean(selectedHistoryKey && transformHistory[selectedHistoryKey]?.length)
  const repinSharedBackgrounds = offering?.repinSharedBackgrounds ?? {}
  const sharedEraserVersionKey = String(sourceVersion)
  const sharedEraserState = repinSharedBackgrounds[sharedEraserVersionKey]
  const sharedEraserApplied = hasManualEraserBackground(sharedEraserState)
  const canUndoEraser = Boolean(sharedEraserState?.eraserHistory && sharedEraserState.eraserHistory.length > 1)
  const canRedoEraser = Boolean(sharedEraserState?.eraserRedoStack && sharedEraserState.eraserRedoStack.length > 0)
  const canvasBaseBackgroundUrl = originalImageUrl ?? previewImageUrl
  const sharedEraserBackgroundUrl = sharedEraserApplied
    ? sharedEraserState?.repinBackgroundDisplayUrl ?? sharedEraserState?.repinBackgroundUrl ?? null
    : null
  const editingBackgroundUrl = sharedEraserBackgroundUrl ?? canvasBaseBackgroundUrl
  const eraserBackgroundRevision = [
    sharedEraserState?.eraserHistory?.length ?? 0,
    sharedEraserState?.repinBackgroundDisplayUrl ?? sharedEraserState?.repinBackgroundUrl ?? '',
  ].join(':')
  const editingCanvasImageUrl = useMemo(() => {
    if (!editingBackgroundUrl) return null
    if (!sharedEraserApplied) return editingBackgroundUrl
    const separator = editingBackgroundUrl.includes('?') ? '&' : '?'
    return editingBackgroundUrl + separator + 'magicEraserRevision=' + encodeURIComponent(eraserBackgroundRevision)
  }, [editingBackgroundUrl, eraserBackgroundRevision, sharedEraserApplied])
  const staticComponentLayers = components
    .filter(comp => comp !== selectedComp)
    .map(comp => {
      const layerTransform = repinTransforms[comp] ?? defaultTransformFor(comp)
      return {
        transform: layerTransform,
        label: componentLabelFor(comp),
        componentImageUrl: componentImageForId(comp) ?? layerTransform.editableLayerUrl ?? null,
        onSelect: () => {
          setSelectedComp(comp)
          setInspectedVersion(null)
          setEraserMode(false)
          setPlacementPreview(false)
        },
      }
    })
    .filter(layer => Boolean(layer.componentImageUrl))

  const persistTransforms = (nextTransforms: Partial<Record<string, RepinTransform>>) => {
    setLocalRepinTransforms(nextTransforms)
    setRepinTransforms(nextTransforms)
  }

  const persistSharedBackgrounds = (nextBackgrounds: Record<string, RepinSharedBackgroundState>) => {
    setRepinSharedBackgrounds(nextBackgrounds)
  }

  const rememberTransform = (snapshot: RepinTransform) => {
    const key = transformHistoryKey(snapshot.componentId ?? snapshot.componentKey, snapshot.sourceVersion)
    setTransformHistory(prev => {
      const history = prev[key] ?? []
      if (history.length && transformSnapshot(history[history.length - 1]) === transformSnapshot(snapshot)) return prev
      return { ...prev, [key]: [...history, snapshot] }
    })
  }

  const handleTransformEditStart = (snapshot: RepinTransform) => {
    rememberTransform(snapshot)
  }

  const handleTransformChange = (next: RepinTransform) => {
    const componentId = next.componentId ?? selectedComp ?? next.componentKey
    const componentType = componentTypeFor(componentId)
    const normalizedNext = { ...next, componentId, componentKey: componentId as ComponentKey, componentType }
    const current = repinTransforms[componentId]
    if (current && transformSnapshot(current) !== transformSnapshot(normalizedNext)) {
      rememberTransform(current)
    }
    setPlacementPreview(false)
    setCanvasConfirmed(false)
    // Persist canvas edits so refresh and back-forward navigation restore the same repin state.
    persistTransforms({
      ...repinTransforms,
      [componentId]: normalizedNext,
    })
  }


  const handleEraseMask = async (maskDataUrl: string) => {
    if (!transform || !selectedComp || isProcessing) return
    try {
      const activeTransform = { ...transform, componentId: selectedComp, componentKey: selectedComp as ComponentKey, componentType: componentTypeFor(selectedComp) }
      await eraseRepinBackground(activeTransform, maskDataUrl, sourceVersion, sourceBaseMode)
      setCanvasConfirmed(false)
      setEraserMode(false)
      setPlacementPreview(false)
      toast('Magic Eraser cleaned the selected area')
    } catch (error) {
      console.error('[Step4Repin] Magic Eraser failed', error)
      toast(safeSystemErrorMessage(), 'destructive')
    }
  }


  const handleUndoEraser = () => {
    if (!sharedEraserState || !canUndoEraser) return
    const history = sharedEraserState.eraserHistory ?? []
    const currentEntry = history[history.length - 1]
    const previousEntry = history[history.length - 2]
    if (!currentEntry || !previousEntry) return
    const nextSharedState = sharedBackgroundWithEraserEntry(
      previousEntry,
      history.slice(0, -1),
      [currentEntry, ...(sharedEraserState.eraserRedoStack ?? [])]
    )
    persistSharedBackgrounds({ ...repinSharedBackgrounds, [sharedEraserVersionKey]: nextSharedState })
    setCanvasConfirmed(false)
  }

  const handleRedoEraser = () => {
    if (!sharedEraserState || !canRedoEraser) return
    const [redoEntry, ...remainingRedo] = sharedEraserState.eraserRedoStack ?? []
    if (!redoEntry) return
    const history = sharedEraserState.eraserHistory?.length ? sharedEraserState.eraserHistory : [eraserEntryFromSharedBackground(sharedEraserState)]
    const nextSharedState = sharedBackgroundWithEraserEntry(
      redoEntry,
      [...history, redoEntry],
      remainingRedo
    )
    persistSharedBackgrounds({ ...repinSharedBackgrounds, [sharedEraserVersionKey]: nextSharedState })
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

    persistTransforms({
      ...repinTransforms,
      [selectedComp]: transform,
    })

    setInspectedVersion(null)
    setPlacementPreview(false)
    setCanvasConfirmed(true)
  }

  const handleInspectVersion = (version: PreviewVersion) => {
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
      toast("Confirm all component positions before generating a new preview.", "destructive")
      return
    }
    if (generationLimitReached) {
      toast("Version limit reached. Choose the best saved version to continue to video.", "destructive")
      return
    }

    const capturedSourceVersion = sourceVersion
    const capturedTargetVersion = targetVersion
    const capturedParentFinalImagePath = parentFinalImagePath
    const capturedSourceVersionComponent = sourceVersionComponent
    const capturedSourceVersionComponentId = sourceVersionComponentId
    const capturedSharedEraserState = sharedEraserState
    const capturedSharedEraserApplied = sharedEraserApplied
    const submittedTransforms = components
      .map(comp => {
        const item = repinTransforms[comp] ?? (comp === selectedComp ? transform : defaultTransformFor(comp))
        if (!item) return null
        const activeComponent = comp === selectedComp
        const sameComponent = capturedSourceVersion > 1 && (capturedSourceVersionComponentId ? capturedSourceVersionComponentId === comp : capturedSourceVersionComponent === comp)
        const selectedOriginalComponentAsset = componentImageForId(comp)
        const useEditableLayerFallback = !selectedOriginalComponentAsset
        const baseTransform = transformForRepinSubmit(item, capturedSharedEraserState, activeComponent && sameComponent)
        return {
          ...baseTransform,
          componentId: comp,
          componentKey: comp as ComponentKey,
          componentType: componentTypeFor(comp),
          sourceVersion: capturedSourceVersion,
          targetVersion: capturedTargetVersion,
          rotation: item.rotation || 0,
          skewX: item.skewX || 0,
          skewY: item.skewY || 0,
          editableLayerUrl: useEditableLayerFallback ? item.editableLayerUrl ?? null : null,
          editableLayerPath: useEditableLayerFallback ? item.editableLayerPath ?? null : null,
          repinBackgroundUrl: capturedSharedEraserApplied ? capturedSharedEraserState?.repinBackgroundUrl ?? null : (activeComponent && sameComponent ? item.repinBackgroundUrl ?? null : null),
          repinBackgroundDisplayUrl: capturedSharedEraserApplied ? capturedSharedEraserState?.repinBackgroundDisplayUrl ?? capturedSharedEraserState?.repinBackgroundUrl ?? null : (activeComponent && sameComponent ? item.repinBackgroundDisplayUrl ?? null : null),
          eraserHistory: capturedSharedEraserApplied ? capturedSharedEraserState?.eraserHistory ?? [] : baseTransform.eraserHistory,
          eraserRedoStack: capturedSharedEraserApplied ? capturedSharedEraserState?.eraserRedoStack ?? [] : baseTransform.eraserRedoStack,
          feedbackOption: activeComponent ? feedbackOptions[0] ?? null : null,
          feedbackOptions: activeComponent ? feedbackOptions : [],
          sourceBaseMode,
          sourceVersionComponentId: capturedSourceVersionComponentId,
          sourceVersionComponent: capturedSourceVersionComponent,
          parentVersionId: capturedSourceVersion,
          parentFinalImagePath: capturedParentFinalImagePath,
          activeComponentId: selectedComp,
          activeComponentType: selectedComponentType,
          currentComponentMaskOrCrop: activeComponent ? (item.originalBbox ?? null) : null,
          magicEraserApplied: capturedSharedEraserApplied,
        }
      })
      .filter(Boolean) as RepinTransform[]

    const primaryPayload = submittedTransforms.find(item => item.componentId === selectedComp) ?? submittedTransforms[0]
    if (!primaryPayload) return

    try {
      setGenerationStartedAt(Date.now())
      setGenerationElapsedSeconds(0)
      persistTransforms(Object.fromEntries(submittedTransforms.map(item => [item.componentId ?? item.componentKey, transformWithoutSharedEraserState(item, capturedSharedEraserState)])) as Partial<Record<string, RepinTransform>>)
      await submitRepinPreview(primaryPayload, submittedTransforms)
      toast("Generating combined repin preview")
    } catch (error) {
      console.error('[Step4Repin] Could not start repin preview', error)
      toast(safeSystemErrorMessage(), "destructive")
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
    if (typeof window !== 'undefined') {
      window.localStorage.setItem('kone-selected-output-version:' + offering.id, String(version.version))
    }
    setCurrentOffering({ ...offering, selectedOutputVersion: version.version, outputImageUrl: version.url, previewImagePath: version.url, outputVideoUrl: null, videoGenerated: false, downloadUrl: null })
    goToStep(5)
    navigate(`/projects/${projectId}/offerings/${offeringId}/step/5`)
  }

  const handleSkipVideoGeneration = () => {
    if (!offering?.outputImageUrl) {
      toast("Generate an image preview before skipping video generation.", "destructive")
      return
    }
    const imageUrl = previewImageUrl ?? offering.outputImageUrl
    setCurrentOffering({
      ...offering,
      outputImageUrl: imageUrl,
      previewImagePath: imageUrl,
      outputVideoUrl: null,
      videoGenerated: false,
      downloadUrl: null,
      renderComplete: true,
      pipelineStatus: "preview_ready",
    })
    goToStep(6)
    navigate("/projects/" + projectId + "/offerings/" + offeringId + "/step/6")
  }

  const handleBack = () => {
    navigate("/projects/" + projectId + "/offerings/" + offeringId + "/step/3")
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
          <p className="mt-2 text-[12px] font-semibold text-[#1450F5]">Edit one component at a time</p>
        </div>
        <button onClick={handleBack} className="text-xs font-medium text-[#9CA3AF] transition-colors duration-[120ms] hover:text-[#6B7280]">Back</button>
      </div>

      <div className="mt-4 flex gap-0 border-t border-[#E9ECEF]">
        <div className="relative flex-[3] p-6 pr-3">
          <div className="mb-3 flex items-center justify-end">
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
                key={String(sourceVersion) + ":" + (editingCanvasImageUrl ?? "base")}
                imageUrl={editingCanvasImageUrl}
                transform={transform}
                label={componentLabelFor(selectedComp)}
                componentImageUrl={selectedComponentImageUrl ?? transform.editableLayerUrl ?? null}
                staticLayers={staticComponentLayers}
                eraserEnabled={eraserMode && !placementPreview}
                eraserBrushSize={eraserBrushSize}
                previewOnly={placementPreview}
                showLabel={false}
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
            <p className="text-xs font-semibold text-[#111827]">{selectedComp ? componentLabelFor(selectedComp) : 'Component'}</p>
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
                    className="block rounded-full border border-[#1450F5] bg-[rgba(20,80,245,0.58)] shadow-[0_0_0_1px_rgba(20,80,245,0.28)]"
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
              {isProcessing ? `Generating Version... ${generationElapsedSeconds}s` : canvasConfirmed ? 'Generate Version' : 'Confirm Position'}
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
            <button
              type="button"
              onClick={handleSkipVideoGeneration}
              disabled={isProcessing || !offering?.outputImageUrl}
              className="flex h-8 w-full items-center justify-center rounded-[5px] border border-[#D7E0FF] bg-white text-xs font-semibold text-[#1450F5] transition-colors duration-[120ms] hover:bg-[#F5F8FF] disabled:cursor-not-allowed disabled:opacity-40"
            >
              Skip video generation
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