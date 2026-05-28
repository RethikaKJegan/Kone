import { create } from 'zustand'
import apiClient from '../api/client'
import type { Project } from '../types'

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
    const { data } = await apiClient.post<Project>('/projects', { name })
    set({ projects: [...get().projects, data] })
    return data
  },

  deleteProject: async (id: string) => {
    await apiClient.delete(`/projects/${id}`)
    set({ projects: get().projects.filter(p => p.id !== id) })
  },
}))
