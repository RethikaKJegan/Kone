import { create } from 'zustand'
import apiClient from '../api/client'
import { getGuestSessionId, isGuestSession } from '../api/guestWorkflow'
import type { Offering, OfferingStep, Environment, ComponentKey, ComponentPin } from '../types'

function getGuestData<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function setGuestData(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value))
  } catch {}
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
    componentPins: [],
    annotationsEnabled: true,
    activeAnnotationFilters: [],
    videoMotionStyle: 'zoom-in',
    videoSpeed: 1,
    videoQuality: '1080p',
    renderComplete: false,
    outputImageUrl: null,
    outputVideoUrl: null,
  }
}

interface OfferingState {
  offerings: Record<string, Offering[]>
  currentOffering: Offering | null
  currentStep: OfferingStep
  isProcessing: boolean
  fetchOfferings: (projectId: string) => Promise<void>
  createOffering: (projectId: string) => Promise<Offering>
  setUpload: (file: File) => Promise<void>
  setComponents: (environments: Environment[], components: ComponentKey[]) => Promise<void>
  setPins: (pins: ComponentPin[]) => void
  runAIPlacement: () => Promise<ComponentPin[]>
  setAnnotationState: (enabled: boolean, filters: ComponentKey[]) => void
  setVideoSettings: (
    settings: Partial<Pick<Offering, 'videoMotionStyle' | 'videoSpeed' | 'videoQuality'>>
  ) => void
  triggerRender: () => Promise<void>
  goToStep: (step: OfferingStep) => void
  completeOffering: () => Promise<void>
  setCurrentOffering: (offering: Offering) => void
}

function patchOffering(offering: Offering, updates: Partial<Offering>): Offering {
  return { ...offering, ...updates }
}

function saveGuestOfferings(state: { offerings: Record<string, Offering[]>; currentOffering: Offering | null }) {
  if (!isGuestSession()) return
  setGuestData('guest_offerings', state.offerings)
  if (state.currentOffering) {
    setGuestData('guest_current_offering', state.currentOffering)
  }
}

export const useOfferingStore = create<OfferingState>()((set, get) => ({
  offerings: {},
  currentOffering: null,
  currentStep: 1,
  isProcessing: false,

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
    set(state => ({ offerings: { ...state.offerings, [projectId]: data } }))
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
    set(state => ({
      offerings: {
        ...state.offerings,
        [projectId]: [...(state.offerings[projectId] ?? []), data],
      },
      currentOffering: data,
      currentStep: 1,
    }))
    return data
  },

  setCurrentOffering: offering => set(state => {
    saveGuestOfferings({ offerings: state.offerings, currentOffering: offering })
    return { currentOffering: offering }
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
      })
      set(state => {
        saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
        return { currentOffering: updated }
      })
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

      // Persist file metadata and imageId — blob URL stays client-side only
      await apiClient.patch(`/offerings/${currentOffering.id}`, {
        imageId,
        uploadedFileName: file.name,
        uploadedFileType: file.type.startsWith('video') ? 'video' : 'image',
      })
    }

    const updates: Partial<Offering> = {
      uploadedFileUrl: fileUrl,
      uploadedFileName: file.name,
      uploadedFileType: file.type.startsWith('video') ? 'video' : 'image',
      ...(imageId ? { imageId } : {}),
    }
    const updated = patchOffering(currentOffering, updates)
    set(state => {
      saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
      return { currentOffering: updated }
    })
  },

  setComponents: async (environments, components) => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const updates: Partial<Offering> = {
      environments,
      selectedComponents: components,
      componentPins: [],
      activeAnnotationFilters: components,
    }
    if (isGuestSession()) {
      const sessionId = await getGuestSessionId()
      apiClient.post('/guest/components', {
        is_guest: true,
        session_id: sessionId,
        project_id: currentOffering.projectId,
        project_name: currentOffering.name,
        environments,
        selected_components: components,
      }).catch(() => {})
    } else {
      apiClient.patch(`/offerings/${currentOffering.id}`, updates)

      // Drive the video pipeline steps if an imageId exists
      if (currentOffering.imageId) {
        apiClient.post('/video/select-environment', {
          imageId: currentOffering.imageId,
          environment: environments[0] ?? '',
        })
        apiClient.post('/video/select-components', {
          imageId: currentOffering.imageId,
          components,
        })
      }
    }
    const updated = patchOffering(currentOffering, updates)
    set(state => {
      saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
      return { currentOffering: updated }
    })
  },

  setPins: pins => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, { componentPins: pins })
    }
    const updated = patchOffering(currentOffering, { componentPins: pins })
    set(state => {
      saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
      return { currentOffering: updated }
    })
  },

  runAIPlacement: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return []
    set({ isProcessing: true })
    try {
      if (isGuestSession()) {
        await new Promise(r => setTimeout(r, 800))
        const { AI_PLACEMENT_DEFAULTS } = await import('../lib/constants')
        const pins: ComponentPin[] = currentOffering.selectedComponents.map(key => ({
          componentKey: key,
          x: AI_PLACEMENT_DEFAULTS[key]?.x ?? 50,
          y: AI_PLACEMENT_DEFAULTS[key]?.y ?? 50,
          aiPlaced: true,
        }))
        const updated = patchOffering(currentOffering, { componentPins: pins })
        set(state => {
          saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
          return { currentOffering: updated, isProcessing: false }
        })
        return pins
      }
      const { data } = await apiClient.post<ComponentPin[]>(
        `/offerings/${currentOffering.id}/ai-placement`
      )
      set({
        currentOffering: patchOffering(currentOffering, { componentPins: data }),
        isProcessing: false,
      })
      return data
    } catch {
      set({ isProcessing: false })
      return []
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
    set(state => {
      saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
      return { currentOffering: updated }
    })
  },

  setVideoSettings: settings => {
    const { currentOffering } = get()
    if (!currentOffering) return
    if (!isGuestSession()) {
      apiClient.patch(`/offerings/${currentOffering.id}`, settings)
    }
    const updated = patchOffering(currentOffering, settings)
    set(state => {
      saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
      return { currentOffering: updated }
    })
  },

  triggerRender: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return
    set({ isProcessing: true })
    try {
      if (isGuestSession()) {
        await new Promise(r => setTimeout(r, 1200))
        const updated = patchOffering(currentOffering, { renderComplete: true })
        set(state => {
          saveGuestOfferings({ offerings: state.offerings, currentOffering: updated })
          return { currentOffering: updated, isProcessing: false }
        })
        return
      }

      // Call video pipeline generate if imageId is available
      if (currentOffering.imageId) {
        await apiClient.post('/video/generate', { imageId: currentOffering.imageId })
      }

      // Mark offering as render complete in the backend
      const { data } = await apiClient.post<Offering>(
        `/offerings/${currentOffering.id}/render`
      )
      set({ currentOffering: data, isProcessing: false })
    } catch {
      set({ isProcessing: false })
    }
  },

  goToStep: step => set({ currentStep: step }),

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
