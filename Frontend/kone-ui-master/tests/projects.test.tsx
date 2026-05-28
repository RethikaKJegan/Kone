import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { projectHandlers } from '../src/mocks/handlers/projects'
import { authHandlers } from '../src/mocks/handlers/auth'
import apiClient from '../src/api/client'

const server = setupServer(...authHandlers, ...projectHandlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

async function signIn() {
  const res = await apiClient.post('/api/auth/signin', {
    email: 'pavan@bellcorpstudio.com',
    password: 'password123',
  })
  localStorage.setItem('salesnxt_token', res.data.token)
  return res.data.token
}

describe('projects API', () => {
  it('fetches seeded projects for authenticated user', async () => {
    await signIn()
    const res = await apiClient.get('/api/projects')
    expect(Array.isArray(res.data)).toBe(true)
    expect(res.data.length).toBeGreaterThan(0)
    expect(res.data[0]).toHaveProperty('name')
  })

  it('creates a new project', async () => {
    await signIn()
    const res = await apiClient.post('/api/projects', { name: 'Test Project' })
    expect(res.data.name).toBe('Test Project')
    expect(res.data.status).toBe('draft')
    expect(res.status).toBe(201)
  })

  it('rejects project name that is too short', async () => {
    await signIn()
    try {
      await apiClient.post('/api/projects', { name: 'X' })
      expect.fail('should have thrown')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status: number } }
      expect(axiosErr.response?.status).toBe(400)
    }
  })

  it('deletes a project', async () => {
    await signIn()
    const createRes = await apiClient.post('/api/projects', { name: 'To Delete' })
    const id = createRes.data.id
    const deleteRes = await apiClient.delete(`/api/projects/${id}`)
    expect(deleteRes.status).toBe(204)
  })
})
