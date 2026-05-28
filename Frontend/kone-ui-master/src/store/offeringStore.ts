import { create } from 'zustand'
import apiClient from '../api/client'
import type { Offering, OfferingStep, Environment, ComponentKey, ComponentPin } from '../types'

interface OfferingState {
  offerings: Record<string, Offering[]>
  currentOffering: Offering | null
  currentStep: OfferingStep
  isProcessing: boolean
  fetchOfferings: (projectId: string) => Promise<void>
  createOffering: (projectId: string) => Promise<Offering>
  setUpload: (file: File) => Promise<void>
  setComponents: (environments: Environment[], components: ComponentKey[]) => Promise<void>
  setPins: (pins: ComponentPin[]) => Promise<void>
  runAIPlacement: () => Promise<ComponentPin[]>
  setAnnotationState: (enabled: boolean, filters: ComponentKey[]) => Promise<void>
  setVideoSettings: (
    settings: Partial<Pick<Offering, 'videoMotionStyle' | 'videoSpeed' | 'videoQuality'>>
  ) => Promise<void>
  triggerRender: () => Promise<void>
  goToStep: (step: OfferingStep) => void
  completeOffering: () => Promise<void>
  setCurrentOffering: (offering: Offering) => void
}

function patchOffering(offering: Offering, updates: Partial<Offering>): Offering {
  return { ...offering, ...updates }
}

export const useOfferingStore = create<OfferingState>()((set, get) => ({
  offerings: {},
  currentOffering: null,
  currentStep: 1,
  isProcessing: false,

  fetchOfferings: async projectId => {
    const { data } = await apiClient.get<Offering[]>(`/projects/${projectId}/offerings`)
    set(state => ({ offerings: { ...state.offerings, [projectId]: data } }))
  },

  createOffering: async projectId => {
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

  setCurrentOffering: offering => set({ currentOffering: offering }),

  setUpload: async (file: File) => {
    const { currentOffering } = get()
    if (!currentOffering) return

    const fileUrl = URL.createObjectURL(file)
    let imageId: string | null = null

    const formData = new FormData()
    formData.append('image', file)
    const { data: uploadData } = await apiClient.post<{ success: boolean; imageId: string }>(
      '/video/upload-image',
      formData
    )
    imageId = uploadData.imageId

    await apiClient.patch(`/offerings/${currentOffering.id}`, {
      imageId,
      uploadedFileName: file.name,
      uploadedFileType: file.type.startsWith('video') ? 'video' : 'image',
    })

    const updates: Partial<Offering> = {
      uploadedFileUrl: fileUrl,
      uploadedFileName: file.name,
      uploadedFileType: file.type.startsWith('video') ? 'video' : 'image',
      ...(imageId ? { imageId } : {}),
    }
    const updated = patchOffering(currentOffering, updates)
    set({ currentOffering: updated })
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
    const { data } = await apiClient.patch<Offering>(`/offerings/${currentOffering.id}`, updates)

    if (currentOffering.imageId) {
      if (environments[0]) {
        await apiClient.post('/video/select-environment', {
          imageId: currentOffering.imageId,
          environment: environments[0],
        })
      }
      await apiClient.post('/video/select-components', {
        imageId: currentOffering.imageId,
        components,
      })
    }
    set({ currentOffering: data })
  },

  setPins: async pins => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const { data } = await apiClient.patch<Offering>(`/offerings/${currentOffering.id}`, { componentPins: pins })
    set({ currentOffering: data })
  },

  runAIPlacement: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return []
    set({ isProcessing: true })
    try {
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

  setAnnotationState: async (enabled, filters) => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const updates: Partial<Offering> = { annotationsEnabled: enabled, activeAnnotationFilters: filters }
    const { data } = await apiClient.patch<Offering>(`/offerings/${currentOffering.id}`, updates)
    set({ currentOffering: data })
  },

  setVideoSettings: async settings => {
    const { currentOffering } = get()
    if (!currentOffering) return
    const { data } = await apiClient.patch<Offering>(`/offerings/${currentOffering.id}`, settings)
    set({ currentOffering: data })
  },

  triggerRender: async () => {
    const { currentOffering } = get()
    if (!currentOffering) return
    set({ isProcessing: true })
    try {
      if (currentOffering.imageId) {
        await apiClient.post('/video/generate', { imageId: currentOffering.imageId })
      }

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
