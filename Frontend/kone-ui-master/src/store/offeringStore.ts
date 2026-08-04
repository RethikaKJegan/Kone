import { create } from 'zustand'
import apiClient from '../api/client'
import { getGuestSessionId, isGuestSession } from '../api/guestWorkflow'
import { KONE_COMPONENTS } from '../lib/constants'
import { useProjectStore } from './projectStore'
import type { Offering, OfferingStep, Environment, ComponentKey, ComponentPin, RepinTransform } from '../types'

type ComponentAssetMap = Partial<Record<ComponentKey, string>>
type VideoGenerationState = {
  startedAt: number
  motion: Offering['videoMotionStyle']
  quality: Offering['videoQuality']
}

function getGuestData<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key) ?? sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function setGuestData(key: string, value: unknown) {
  try {
    const raw = JSON.stringify(value)
    localStorage.setItem(key, raw)
    sessionStorage.setItem(key, raw)
  } catch {
    // Browser storage can be unavailable or full; guest persistence is best-effort.
  }
}

function refreshProjects() {
  if (!isGuestSession()) {
    useProjectStore.getState().fetchProjects().catch(() => {})
  }
}

function initialOfferingStep(): OfferingStep {
  if (typeof window === 'undefined') return 1
  const step = Number(window.location.pathname.split('/step/').pop())
  return step >= 1 && step <= 6 ? (step as OfferingStep) : 1
}

function makeGuestOffering(projectId: string): Offering {
  return {
    id: `guest_off_${Date.now()}`,
    projectId,
    name: 'New Visualization',
    status: 'draft',
    createdAt: new Date().toISOString(),
    imageId: null,
    uploadedFileUrl: null,
    uploadedFileName: null,
    uploadedFileType: null,
    environments: [],
    selectedComponents: [],
    selectedComponentAssets: {},
    componentPins: [],
    annotationsEnabled: true,
    activeAnnotationFilters: [],
    videoMotionStyle: 'zoom-in',
    videoSpeed: 1,
    videoQuality: '1080p',
    renderComplete: false,
    outputImageUrl: null,
    outputVideoUrl: null,
    savedStep: 1,
    previewRequestKey: null,
    previewVersions: [],
    repinPass: 0,
    videoGenerated: false,
    downloadUrl: null,
  }
}

interface OfferingState {
  offerings: Record<string, Offering[]>
  currentOffering: Offering | null
  currentStep: OfferingStep
  isProcessing: boolean
  videoGenerations: Record<string, VideoGenerationState>
  fetchOfferings: (projectId: string) => Promise<void>
  createOffering: (projectId: string) => Promise<Offering>
  updateOfferingName: (projectId: string, offeringId: string, name: string) => Promise<Offering>
  deleteOffering: (projectId: string, offeringId: string) => Promise<void>
  setUpload: (file: File) => Promise<void>
  setComponents: (environments: Environment[], components: ComponentKey[], componentAssets?: ComponentAssetMap) => Promise<void>
  setPins: (pins: ComponentPin[]) => void
  setRepinTransforms: (transforms: Partial<Record<ComponentKey, RepinTransform>>) => void
  runAIPlacement: () => Promise<ComponentPin[]>
  submitRepinPreview: (transform: RepinTransform) => Promise<void>
  eraseRepinBackground: (transform: RepinTransform, maskDataUrl: string, sourceVersion: number, sourceBaseMode: 'original' | 'version') => Promise<RepinTransform>
  setAnnotationState: (enabled: boolean, filters: ComponentKey[]) => void
  setVideoSettings: (
    settings: Partial<Pick<Offering, 'videoMotionStyle' | 'videoSpeed' | 'videoQuality'>>
  ) => void
  setDownloadReady: (downloadUrl: string | null) => void
  triggerRender: () => Promise<void>
  goToStep: (step: OfferingStep) => void
  completeOffering: () => Promise<void>
  setCurrentOffering: (offering: Offering) => void
  startVideoGeneration: (offeringId: string, generation: VideoGenerationState) => void
  finishVideoGeneration: (offeringId: string) => void
}

function patchOffering(offering: Offering, updates: Partial<Offering>): Offering {
  return { ...offering, ...updates }
}


function eraserEntryFromTransform(transform: RepinTransform) {
  return {
    repinBackgroundUrl: transform.repinBackgroundUrl ?? null,
    repinBackgroundDisplayUrl: transform.repinBackgroundDisplayUrl ?? transform.repinBackgroundUrl ?? null,
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

function normalizeOffering(offering: Offering): Offering {
  const uploadedFileUrl = offering.uploadedFileUrl ?? offering.inputImagePath ?? null
  const outputImageUrl = offering.outputImageUrl ?? offering.outputImagePath ?? null
  const outputVideoUrl = offering.outputVideoUrl ?? offering.outputVideoPath ?? null
  return {
    ...offering,
    uploadedFileUrl,
    outputImageUrl,
    outputVideoUrl,
    renderComplete: Boolean(offering.renderComplete ?? outputImageUrl),
    savedStep: offering.savedStep ?? 1,
    videoGenerated: Boolean(offering.videoGenerated ?? outputVideoUrl),
    downloadUrl: offering.downloadUrl ?? null,
    previewVersions: offering.previewVersions ?? (outputImageUrl ? [{ version: 1, url: outputImageUrl }] : []),
    repinPass: offering.repinPass ?? (offering.previewVersions?.length || (outputImageUrl ? 1 : 0)),
    repinTransforms: offering.repinTransforms ?? {},
    selectedComponentAssets: offering.selectedComponentAssets ?? {},
  }
}

function saveGuestOfferings(state: { offerings: Record<string, Offering[]>; currentOffering: Offering | null }) {
  if (!isGuestSession()) return
  setGuestData('guest_offerings', state.offerings)
  if (state.currentOffering) {
    setGuestData('guest_current_offering', state.currentOffering)
  }
}

function componentSignature(environments: Environment[], components: ComponentKey[], componentAssets: ComponentAssetMap = {}) {
  return JSON.stringify({
    environments: [...environments].sort(),
    components: [...components].sort(),
    componentAssets: Object.fromEntries(
      Object.entries(componentAssets)
        .filter(([, value]) => Boolean(value))
        .sort(([a], [b]) => a.localeCompare(b))
    ),
  })
}

function defaultComponentAsset(componentKey: ComponentKey) {
  const component = KONE_COMPONENTS.find(item => item.key === componentKey)
  return component?.variants?.[0]?.imageUrl ?? component?.imageUrl ?? null
}

function componentAssetMap(components: ComponentKey[], selectedAssets: ComponentAssetMap = {}) {
  return Object.fromEntries(
    components
      .map(componentKey => [componentKey, selectedAssets[componentKey] ?? defaultComponentAsset(componentKey)] as const)
      .filter(([, value]) => Boolean(value))
  ) as ComponentAssetMap
}

function isHttpStatus(error: unknown, status: number) {
  return Boolean(
    error &&
      typeof error === 'object' &&
      'response' in error &&
      (error as { response?: { status?: number } }).response?.status === status
  )
}

function imageIdFromOffering(offering: Offering | null) {
  if (!offering) return null
  if (offering.imageId) return offering.imageId
  const fromInput = offering.inputImagePath?.match(/\/uploads\/([^/]+)\/input\.jpg(?:\?.*)?$/)
  if (fromInput?.[1]) return fromInput[1]
  const fromOutput = (offering.outputImageUrl || offering.uploadedFileUrl || '').match(/\/output\/([^/?]+)\/final_output\.png(?:\?.*)?$/)
  return fromOutput?.[1] ?? null
}

function writeOfferingState(state: OfferingState, offering: Offering) {
  const normalized = normalizeOffering(offering)
  const projectOfferings = state.offerings[normalized.projectId] ?? []
  const exists = projectOfferings.some(o => o.id === normalized.id)
  const offerings = {
    ...state.offerings,
    [normalized.projectId]: exists
      ? projectOfferings.map(o => (o.id === normalized.id ? normalized : o))
      : [...projectOfferings, normalized],
  }
  saveGuestOfferings({ offerings, currentOffering: normalized })
  return { offerings, currentOffering: normalized }
}

export const useOfferingStore = create<OfferingState>()((set, get) => ({
  offerings: {},
  currentOffering: null,
  currentStep: initialOfferingStep(),
  isProcessing: false,
  videoGenerations: {},

  fetchOfferings: async projectId => {
    if (isGuestSession()) {
      const cached = getGuestData<Record<string, Offering[]>>('guest_offerings')
      const projectOfferings = cached?.[projectId] ?? []
      set(state => ({
        offerings: { ...state.offerings, [projectId]: projectOfferings },
      }))
      return
    }
    const { data } = await apiClient.get<Offering[]>(`/projects/${projectId}/offerings`)
    set(state => ({ offerings: { ...state.offerings, [projectId]: data.map(normalizeOffering) } }))
  },

  createOffering: async projectId => {
    if (isGuestSession()) {
      const offering = makeGuestOffering(projectId)
      set(state => {
        const updated = {
          offerings: {
            ...state.offerings,
            [projectId]: [...(state.offerings[projectId] ?? []), offering],
          },
          currentOffering: offering,
          currentStep: 1 as OfferingStep,
        }
        saveGuestOfferings({ offerings: updated.offerings, currentOffering: offering })
        return updated
      })
      return offering
    }
    const { data } = await apiClient.post<Offering>(`/projects/${projectId}/offerings`)
    const offering = normalizeOffering(data)
    refreshProjects()
    set(state => ({
      offerings: {
        ...state.offerings,
        [projectId]: [...(state.offerings[projectId] ?? []), offering],
      },
      currentOffering: offering,
      currentStep: 1,
    }))
    return offering
  },

  updateOfferingName: async (projectId, offeringId, name) => {
    if (isGuestSession()) {
      const current = get().offerings[projectId] ?? []
      const updated = current.map(o =>
        o.id === offeringId ? normalizeOffering({ ...o, name }) : o
      )
      const offering = updated.find(o => o.id === offeringId)
      if (!offering) throw new Error('Visualization not found')
      set(state => ({
        offerings: { ...state.offerings, [projectId]: updated },
        currentOffering: state.currentOffering?.id === offeringId ? offering : state.currentOffering,
      }))
      return offering
    }
    const { data } = await apiClient.patch<Offering>(
      `/projects/${projectId}/visualizations/${offeringId}`,
      { name }
    )
    const offering = normalizeOffering(data)
    refreshProjects()
    set(state => {
      const current = state.offerings[projectId] ?? []
      return {
        offerings: {
          ...state.offerings,
          [projectId]: current.map(o => (o.id === offeringId ? offering : o)),
        },
        currentOffering: state.currentOffering?.id === offeringId ? offering : state.currentOffering,
      }
    })
    return offering
  },

  deleteOffering: async (projectId, offeringId) => {
    if (isGuestSession()) {
      set(state => {
        const remaining = (state.offerings[projectId] ?? []).filter(o => o.id !== offeringId)
        const currentOffering = state.currentOffering?.id === offeringId
          ? remaining[0] ?? null
          : state.currentOffering
        const offerings = { ...state.offerings, [projectId]: remaining }
        saveGuestOfferings({ offerings, currentOffering })
        return { offerings, currentOffering, currentStep: currentOffering?.savedStep ?? 1 }
      })
      return
    }
    await apiClient.delete(`/projects/${projectId}/visualizations/${offeringId}`)
    refreshProjects()
    set(state => {
      const remaining = (state.offerings[projectId] ?? []).filter(o => o.id !== offeringId)
      const currentOffering = state.currentOffering?.id === offeringId
        ? remaining[0] ?? null
        : state.currentOffering
      return {
        offerings: { ...state.offerings, [projectId]: remaining },
        currentOffering,
        currentStep: currentOffering?.savedStep ?? 1,
      }
    })
  },


  setCurrentOffering: offering => set(state => {
    const normalized = normalizeOffering(offering)
    const savedStep = normalized.savedStep ?? state.currentStep ?? 1
    return { ...writeOfferingState(state, { ...normalized, savedStep }), currentStep: savedStep }
  }),

  startVideoGeneration: (offeringId, generation) => set(state => ({
    videoGenerations: {
      ...state.videoGenerations,
      [offeringId]: generation,
    },
  })),

  finishVideoGeneration: offeringId => set(state => {
    const { [offeringId]: _finished, ...videoGenerations } = state.videoGenerations
    return { videoGenerations }
  }),

  setUpload: async (file: File) => {
    const { currentOffering } = get()
    if (!currentOffering) return

    const fileUrl = URL.createObjectURL(file)
    let imageId: string | null = null

    if (isGuestSession()) {
      const sessionId = await getGuestSessionId()
      const formData = new FormData()
      formData.append('image', file)
      formData.append('session_id', sessionId)
      formData.append('project_id', currentOffering.projectId)
      formData.append('project_name', currentOffering.name)
      formData.append('is_guest', 'true')
      const { data } = await apiClient.post<{ image_url: string }>('/guest/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const updated = patchOffering(currentOffering, {
        uploadedFileUrl: data.image_url,
        uploadedFileName: file.name,
        uploadedFileType: 'image',
        inputImagePath: null,
        previewImagePath: null,
        outputImagePath: null,
        outputVideoPath: null,
        componentPins: [],
        renderComplete: false,
        outputImageUrl: null,
        outputVideoUrl: null,
        videoGenerated: false,
        downloadUrl: null,
        previewVersions: [],
        repinPass: 0,
        repinTransforms: {},
      })
      set(state => writeOfferingState(state, updated))
      return
    }

    if (!isGuestSession()) {
      // Upload to video pipeline to get an imageId for subsequent steps
      const formData = new FormData()
      formData.append('image', file)
      const { data: uploadData } = await apiClient.post<{ success: boolean; imageId: string }>(
        '/video/upload-image',
        formData,
        { headers: { 'Content-Type': undefined } }
      )
      imageId = uploadData.imageId

      // Persist file metadata and imageId; blob URL stays client-side only
      await apiClient.patch('/offerings/' + currentOffering.id, {
        imageId,
        uploadedFileName: file.name,
        uploadedFileType: file.type.startsWith('video') ? 'video' : 'image',
        inputImagePath: '/uploads/' + imageId + '/input.jpg',
        previewImagePath: null,
        outputImagePath: null,
        outputVideoPath: null,
        pipelineStatus: 'uploaded',
      })
      refreshProjects()
    }

    const updates: Partial<Offering> = {
      status: 'active',
      uploadedFileUrl: fileUrl,
      uploadedFileName: file.name,
      uploadedFileType: file.type.startsWith('video') ? 'video' : 'image',
      inputImagePath: imageId ? '/uploads/' + imageId + '/input.jpg' : null,
      previewImagePath: null,
      outputImagePath: null,
      outputVideoPath: null,
      componentPins: [],
      renderComplete: false,
      outputImageUrl: null,
      outputVideoUrl: null,
      previewRequestKey: null,
      videoGenerated: false,
      downloadUrl: null,
      previewVersions: [],
      repinPass: 0,
      repinTransforms: {},
      ...(imageId ? { imageId } : {}),
    }
    const updated = patchOffering(currentOffering, updates)
    set(state => writeOfferingState(state, updated))
  },

  setComponents: async (environments, components, selectedAssets = {}) => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const selectedComponents = components
    const selectedComponentAssets = componentAssetMap(selectedComponents, selectedAssets)
    const previewRequestKey = componentSignature(environments, selectedComponents, selectedComponentAssets)
    const updates: Partial<Offering> = {
      status: 'active',
      environments,
      selectedComponents,
      selectedComponentAssets,
      componentPins: [],
      activeAnnotationFilters: selectedComponents,
      renderComplete: false,
      pipelineStatus: 'processing',
      outputImageUrl: null,
      outputVideoUrl: null,
      previewRequestKey,
      videoGenerated: false,
      downloadUrl: null,
      previewVersions: [],
      repinPass: 0,
      repinTransforms: {},
    }
    const updated = patchOffering(currentOffering, updates)
    set(state => writeOfferingState(state, updated))

    if (isGuestSession() && selectedComponents.length > 0) {
      const sessionId = await getGuestSessionId()
      const componentAssets = Object.fromEntries(
        Object.entries(selectedComponentAssets)
      )
      await apiClient.post('/guest/components', {
        is_guest: true,
        session_id: sessionId,
        project_id: currentOffering.projectId,
        project_name: currentOffering.name,
        environments,
        selected_components: selectedComponents,
        component_assets: componentAssets,
        preview_request_key: previewRequestKey,
      })
    } else if (!isGuestSession()) {
      await apiClient.patch(`/offerings/${currentOffering.id}`, {
        environments,
        selectedComponents,
        selectedComponentAssets,
        componentPins: [],
        activeAnnotationFilters: selectedComponents,
        renderComplete: false,
        pipelineStatus: 'processing',
        previewRequestKey,
        outputImageUrl: null,
        outputVideoUrl: null,
        downloadUrl: null,
        previewVersions: [],
        repinPass: 0,
        repinTransforms: {},
      })
      refreshProjects()

      // Drive the video pipeline steps if an imageId exists
      const imageId = imageIdFromOffering(currentOffering)
      if (imageId) {
        await apiClient.post('/video/select-environment', {
          imageId,
          environment: environments[0] ?? '',
        })
        const componentAssets = Object.fromEntries(
          Object.entries(selectedComponentAssets)
        )
        await apiClient.post('/video/select-components', {
          imageId,
          offeringId: currentOffering.id,
          components: selectedComponents,
          environments,
          component_assets: componentAssets,
          preview_request_key: previewRequestKey,
        })
      }
    }
  },

  setPins: pins => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, { componentPins: pins })
    }
    const updated = patchOffering(currentOffering, { componentPins: pins })
    set(state => writeOfferingState(state, updated))
  },


  setRepinTransforms: transforms => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, { repinTransforms: transforms }).catch(() => {})
    }
    const updated = patchOffering(currentOffering, { repinTransforms: transforms })
    set(state => writeOfferingState(state, updated))
  },

  runAIPlacement: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return []
    set({ isProcessing: true })
    try {
      if (isGuestSession()) {
        const sessionId = await getGuestSessionId()
        const { data } = await apiClient.get('/guest/status', {
          params: { session_id: sessionId, project_id: currentOffering.projectId },
        })
        const placementPins = (data.component_pins ?? []) as ComponentPin[]
        const selected = new Set(currentOffering.selectedComponents)
        const pins = placementPins.filter(pin => selected.has(pin.componentKey))
        const updated = patchOffering(currentOffering, { componentPins: pins })
        set(state => ({ ...writeOfferingState(state, updated), isProcessing: false }))
        return pins
      }
      const { data } = await apiClient.post<ComponentPin[]>(
        `/offerings/${currentOffering.id}/ai-placement`
      )
      const updated = patchOffering(currentOffering, { componentPins: data, status: 'active' })
      refreshProjects()
      set(state => ({ ...writeOfferingState(state, updated), isProcessing: false }))
      return data
    } catch {
      set({ isProcessing: false })
      return []
    }
  },



  submitRepinPreview: async transform => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (transform.targetVersion > 5) {
      throw new Error('Version limit reached. Choose the best saved version to continue.')
    }
    set({ isProcessing: true })
    try {
      const previewRequestKey = `repin:${currentOffering.id}:${transform.componentKey}:v${transform.targetVersion}:${Date.now()}`
      const selectedComponents = Array.from(new Set([
        ...(currentOffering.selectedComponents.length ? currentOffering.selectedComponents : []),
        transform.componentKey,
      ]))
      const selectedComponentAssets = componentAssetMap(selectedComponents, currentOffering.selectedComponentAssets)
      const confirmedRepinTransforms = {
        ...(currentOffering.repinTransforms ?? {}),
        [transform.componentKey]: transform,
      }
      const updated = patchOffering(currentOffering, {
        pipelineStatus: 'processing',
        previewRequestKey,
        outputVideoUrl: null,
        videoGenerated: false,
        downloadUrl: null,
        repinTransforms: confirmedRepinTransforms,
      })
      set(state => writeOfferingState(state, updated))

      if (isGuestSession()) {
        const sessionId = await getGuestSessionId()
        const componentAssets = Object.fromEntries(
          Object.entries(selectedComponentAssets)
        )
        await apiClient.post('/guest/repin', {
          is_guest: true,
          session_id: sessionId,
          project_id: currentOffering.projectId,
          project_name: currentOffering.name,
          selected_components: selectedComponents,
          component_assets: componentAssets,
          environments: currentOffering.environments,
          preview_request_key: previewRequestKey,
          transform,
          transforms: Object.values(confirmedRepinTransforms).filter(Boolean),
        }, { timeout: 0 })
      } else {
        const imageId = imageIdFromOffering(currentOffering)
        if (!imageId) throw new Error('Uploaded image is not ready for repin')
        const componentAssets = Object.fromEntries(
          Object.entries(selectedComponentAssets)
        )
        await apiClient.post('/video/repin', {
          imageId,
          offeringId: currentOffering.id,
          components: selectedComponents,
          environments: currentOffering.environments,
          component_assets: componentAssets,
          preview_request_key: previewRequestKey,
          transform,
          transforms: Object.values(confirmedRepinTransforms).filter(Boolean),
        }, { timeout: 0 })
      }
    } catch (error) {
      set({ isProcessing: false })
      const response = error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { message?: string; error?: string } } }).response
        : null
      const message = response?.data?.message || response?.data?.error
      throw new Error(message || (error instanceof Error ? error.message : 'Could not start repin preview'))
    }
  },


  eraseRepinBackground: async (transform, maskDataUrl, sourceVersion, sourceBaseMode) => {
    const { currentOffering } = get()
    if (!currentOffering) throw new Error('Offering is not ready')
    set({ isProcessing: true })
    try {
      let result: { repinBackgroundUrl: string; repinBackgroundDisplayUrl: string }
      if (isGuestSession()) {
        const sessionId = await getGuestSessionId()
        const { data } = await apiClient.post('/guest/repin/erase', {
          is_guest: true,
          session_id: sessionId,
          project_id: currentOffering.projectId,
          project_name: currentOffering.name,
          source_version: sourceVersion,
          source_base_mode: sourceBaseMode,
          mask_data_url: maskDataUrl,
          transform,
        }, { timeout: 0 })
        result = {
          repinBackgroundUrl: data.repinBackgroundUrl,
          repinBackgroundDisplayUrl: data.repinBackgroundDisplayUrl ?? data.repinBackgroundUrl,
        }
      } else {
        const imageId = imageIdFromOffering(currentOffering)
        if (!imageId) throw new Error('Uploaded image is not ready for Magic Eraser')
        const { data } = await apiClient.post('/video/repin/erase', {
          imageId,
          offeringId: currentOffering.id,
          sourceVersion,
          sourceBaseMode,
          maskDataUrl,
          transform,
        }, { timeout: 0 })
        result = {
          repinBackgroundUrl: data.repinBackgroundUrl,
          repinBackgroundDisplayUrl: data.repinBackgroundDisplayUrl ?? data.repinBackgroundUrl,
        }
      }
      const nextEntry = {
        repinBackgroundUrl: result.repinBackgroundUrl,
        repinBackgroundDisplayUrl: result.repinBackgroundDisplayUrl,
      }
      const eraserHistory = transform.eraserHistory?.length ? transform.eraserHistory : [eraserEntryFromTransform(transform)]
      const nextTransform = transformWithEraserEntry(transform, nextEntry, [...eraserHistory, nextEntry], [])
      const repinTransforms = {
        ...(currentOffering.repinTransforms ?? {}),
        [transform.componentKey]: nextTransform,
      }
      const updated = patchOffering(currentOffering, { repinTransforms })
      set(state => ({ ...writeOfferingState(state, updated), isProcessing: false }))
      if (!isGuestSession()) {
        apiClient.patch(`/offerings/${currentOffering.id}`, { repinTransforms }).catch(() => {})
      }
      return nextTransform
    } catch (error) {
      set({ isProcessing: false })
      const response = error && typeof error === 'object' && 'response' in error
        ? (error as { response?: { data?: { message?: string; error?: string } } }).response
        : null
      const message = response?.data?.message || response?.data?.error
      throw new Error(message || (error instanceof Error ? error.message : 'Magic Eraser failed'))
    }
  },

  setAnnotationState: (enabled, filters) => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const updates: Partial<Offering> = { annotationsEnabled: enabled, activeAnnotationFilters: filters }
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, updates)
    }
    const updated = patchOffering(currentOffering, updates)
    set(state => writeOfferingState(state, updated))
  },

  setVideoSettings: settings => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, settings)
    }
    const updated = patchOffering(currentOffering, {
      ...settings,
    })
    set(state => writeOfferingState(state, updated))
  },

  setDownloadReady: downloadUrl => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const updated = patchOffering(currentOffering, { downloadUrl, savedStep: 6 })
    set(state => ({ ...writeOfferingState(state, updated), currentStep: 6 }))
  },

  triggerRender: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return
    set({ isProcessing: true })
    try {
      if (isGuestSession()) {
        await new Promise(r => setTimeout(r, 1200))
        const updated = patchOffering(currentOffering, { renderComplete: true })
        set(state => ({ ...writeOfferingState(state, updated), isProcessing: false }))
        return
      }

      // Call video pipeline generate if imageId is available
      const imageId = imageIdFromOffering(currentOffering)
      if (imageId) {
        try {
          await apiClient.post('/video/generate', {
            imageId,
            sourceImageUrl:  currentOffering.outputImagePath ?? currentOffering.outputImageUrl ?? currentOffering.uploadedFileUrl ?? undefined,
            videoOptions: {
              motion: currentOffering.videoMotionStyle,
              speed: currentOffering.videoSpeed,
              quality: currentOffering.videoQuality,
            },
          })
        } catch (error) {
          if (!isHttpStatus(error, 404) || currentOffering.videoMotionStyle === 'door-functionality') {
            throw error
          }
        }
      }

      // Mark offering as render complete in the backend
      const { data } = await apiClient.post<Offering>(
        `/offerings/${currentOffering.id}/render`
      )
      const updated = patchOffering(currentOffering, data)
      refreshProjects()
      set(state => ({ ...writeOfferingState(state, updated), isProcessing: false }))
    } catch (error) {
      set({ isProcessing: false })
      throw error
    }
  },

  goToStep: step => set(state => {
    const currentOffering = state.currentOffering
    if (!currentOffering) return { currentStep: step }
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, { savedStep: step }).catch(() => {})
    }
    const updated = patchOffering(currentOffering, { savedStep: step })
    return { ...writeOfferingState(state, updated), currentStep: step }
  }),

  completeOffering: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (isGuestSession()) {
      const updated = patchOffering(currentOffering, { status: 'complete' })
      set(state => {
        const projectOfferings = state.offerings[currentOffering.projectId] ?? []
        const newOfferings = {
          ...state.offerings,
          [currentOffering.projectId]: projectOfferings.map(o =>
            o.id === updated.id ? updated : o
          ),
        }
        saveGuestOfferings({ offerings: newOfferings, currentOffering: updated })
        return { currentOffering: updated, offerings: newOfferings }
      })
      return
    }
    const { data } = await apiClient.post<Offering>(
      `/offerings/${currentOffering.id}/complete`
    )
    refreshProjects()
    set(state => {
      const projectOfferings = state.offerings[currentOffering.projectId] ?? []
      return {
        currentOffering: data,
        offerings: {
          ...state.offerings,
          [currentOffering.projectId]: projectOfferings.map(o =>
            o.id === data.id ? data : o
          ),
        },
      }
    })
  },
}))
