import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { offeringHandlers } from '../src/mocks/handlers/offerings'
import { projectHandlers } from '../src/mocks/handlers/projects'
import { authHandlers } from '../src/mocks/handlers/auth'
import apiClient from '../src/api/client'

const server = setupServer(...authHandlers, ...projectHandlers, ...offeringHandlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

async function setup() {
  const authRes = await apiClient.post('/api/auth/signin', {
    email: 'pavan@bellcorpstudio.com',
    password: 'password123',
  })
  localStorage.setItem('salesnxt_token', authRes.data.token)
  const projRes = await apiClient.post('/api/projects', { name: 'Offering Test Project' })
  return projRes.data.id as string
}

describe('offerings API', () => {
  it('creates a new offering', async () => {
    const projectId = await setup()
    const res = await apiClient.post(`/api/projects/${projectId}/offerings`)
    expect(res.data.projectId).toBe(projectId)
    expect(res.data.status).toBe('draft')
    expect(res.status).toBe(201)
  })

  it('patches offering fields', async () => {
    const projectId = await setup()
    const offeringRes = await apiClient.post(`/api/projects/${projectId}/offerings`)
    const id = offeringRes.data.id
    const patchRes = await apiClient.patch(`/api/offerings/${id}`, {
      environments: ['car'],
      selectedComponents: ['ceiling', 'cop'],
    })
    expect(patchRes.data.environments).toEqual(['car'])
    expect(patchRes.data.selectedComponents).toEqual(['ceiling', 'cop'])
  })

  it('runs AI placement and returns deterministic pins', async () => {
    const projectId = await setup()
    const offeringRes = await apiClient.post(`/api/projects/${projectId}/offerings`)
    const id = offeringRes.data.id
    await apiClient.patch(`/api/offerings/${id}`, { selectedComponents: ['ceiling', 'lci'] })
    const placementRes = await apiClient.post(`/api/offerings/${id}/ai-placement`)
    expect(Array.isArray(placementRes.data)).toBe(true)
    expect(placementRes.data).toHaveLength(2)
    const ceilingPin = placementRes.data.find((p: { componentKey: string }) => p.componentKey === 'ceiling')
    expect(ceilingPin).toMatchObject({ x: 50, y: 10, aiPlaced: true })
  }, 10000)

  it('completes an offering', async () => {
    const projectId = await setup()
    const offeringRes = await apiClient.post(`/api/projects/${projectId}/offerings`)
    const id = offeringRes.data.id
    const completeRes = await apiClient.post(`/api/offerings/${id}/complete`)
    expect(completeRes.data.status).toBe('complete')
  })
})
