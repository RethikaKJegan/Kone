import type { User, Project, Offering, Brochure } from '../../types'
import { generateId } from '../../lib/utils'

export const SEEDED_USER: User = {
  id: 'user-1',
  email: 'pavan@bellcorpstudio.com',
  name: 'Pavan Kumar',
  role: 'authenticated',
  company: 'KONE',
  avatarInitials: 'PK',
}

export const users: Map<string, User & { password: string }> = new Map([
  [
    'pavan@bellcorpstudio.com',
    { ...SEEDED_USER, password: 'password123' },
  ],
])

export const tokens: Map<string, string> = new Map()

export const projects: Map<string, Project> = new Map([
  [
    'proj-1',
    {
      id: 'proj-1',
      name: 'Dubai Tower',
      status: 'draft',
      createdAt: '2026-05-21T00:00:00.000Z',
      updatedAt: '2026-05-21T00:00:00.000Z',
      offeringCount: 0,
      userId: 'user-1',
    },
  ],
  [
    'proj-2',
    {
      id: 'proj-2',
      name: 'Helsinki HQ',
      status: 'active',
      createdAt: '2026-05-18T00:00:00.000Z',
      updatedAt: '2026-05-18T00:00:00.000Z',
      offeringCount: 1,
      userId: 'user-1',
    },
  ],
])

export const offerings: Map<string, Offering> = new Map([
  [
    'off-1',
    {
      id: 'off-1',
      projectId: 'proj-2',
      name: 'Offering 1',
      status: 'complete',
      createdAt: '2026-05-18T00:00:00.000Z',
      imageId: null,
      uploadedFileUrl: null,
      uploadedFileName: 'building-photo.jpg',
      uploadedFileType: 'image',
      environments: ['car', 'lobby'],
      selectedComponents: ['ceiling', 'lci', 'door', 'cop'],
      componentPins: [
        { componentKey: 'ceiling', x: 50, y: 10, aiPlaced: true },
        { componentKey: 'lci', x: 78, y: 40, aiPlaced: true },
        { componentKey: 'door', x: 20, y: 55, aiPlaced: true },
        { componentKey: 'cop', x: 18, y: 52, aiPlaced: true },
      ],
      annotationsEnabled: true,
      activeAnnotationFilters: ['ceiling', 'lci', 'door', 'cop'],
      videoMotionStyle: 'zoom-in',
      videoSpeed: 1,
      videoQuality: '1080p',
      renderComplete: true,
      outputImageUrl: null,
      outputVideoUrl: null,
    },
  ],
])

export const brochures: Map<string, Brochure> = new Map()

export function createProject(name: string, userId: string): Project {
  const id = `proj-${generateId()}`
  const project: Project = {
    id,
    name,
    status: 'draft',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    offeringCount: 0,
    userId,
  }
  projects.set(id, project)
  return project
}

export function createOffering(projectId: string): Offering {
  const id = `off-${generateId()}`
  const project = projects.get(projectId)
  const count = [...offerings.values()].filter(o => o.projectId === projectId).length
  const offering: Offering = {
    id,
    projectId,
    name: `Offering ${count + 1}`,
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
  offerings.set(id, offering)
  if (project) {
    project.offeringCount += 1
    projects.set(projectId, project)
  }
  return offering
}

export function getUserFromToken(authHeader: string | null): User | null {
  if (!authHeader?.startsWith('Bearer ')) return null
  const token = authHeader.slice(7)
  const userId = tokens.get(token)
  if (!userId) return null
  const user = [...users.values()].find(u => u.id === userId)
  return user ?? null
}
