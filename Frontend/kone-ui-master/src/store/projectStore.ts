import { create } from 'zustand'
import apiClient from '../api/client'
import type { Project } from '../types'

function isGuestSession() {
  return sessionStorage.getItem('guest_session') === '1'
}

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

interface ProjectState {
  projects: Project[]
  isLoading: boolean
  error: string | null
  fetchProjects: () => Promise<void>
  createProject: (name: string) => Promise<Project>
  deleteProject: (id: string) => Promise<void>
}

export const useProjectStore = create<ProjectState>()((set, get) => ({
  projects: [],
  isLoading: false,
  error: null,

  fetchProjects: async () => {
    if (isGuestSession()) {
      const cached = getGuestData<Project[]>('guest_projects')
      set({ projects: cached ?? [], isLoading: false, error: null })
      return
    }
    set({ isLoading: true, error: null })
    try {
      const { data } = await apiClient.get<Project[]>('/projects')
      set({ projects: data })
    } catch {
      set({ error: 'Failed to load projects' })
    } finally {
      set({ isLoading: false })
    }
  },

  createProject: async (name: string) => {
    if (isGuestSession()) {
      const project: Project = {
        id: `guest_proj_${Date.now()}`,
        name,
        status: 'draft',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        offeringCount: 0,
        userId: 'guest',
      }
      const updated = [...get().projects, project]
      set({ projects: updated })
      setGuestData('guest_projects', updated)
      return project
    }
    const { data } = await apiClient.post<Project>('/projects', { name })
    set({ projects: [...get().projects, data] })
    return data
  },

  deleteProject: async (id: string) => {
    if (isGuestSession()) {
      const updated = get().projects.filter(p => p.id !== id)
      set({ projects: updated })
      setGuestData('guest_projects', updated)
      return
    }
    await apiClient.delete(`/projects/${id}`)
    set({ projects: get().projects.filter(p => p.id !== id) })
  },
}))
