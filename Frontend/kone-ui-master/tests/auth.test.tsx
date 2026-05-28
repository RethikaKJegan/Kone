import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { setupServer } from 'msw/node'
import { authHandlers } from '../src/mocks/handlers/auth'
import apiClient from '../src/api/client'

const server = setupServer(...authHandlers)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('auth API', () => {
  it('signs in with valid credentials', async () => {
    const res = await apiClient.post('/auth/login', {
      email: 'pavan@bellcorpstudio.com',
      password: 'password123',
    })
    expect(res.data.user.email).toBe('pavan@bellcorpstudio.com')
    expect(res.data.tokens.access.token).toBeTruthy()
  })

  it('signs in with any @kone.com email', async () => {
    const res = await apiClient.post('/auth/login', {
      email: 'test@kone.com',
      password: 'anypassword',
    })
    expect(res.data.user.email).toBe('test@kone.com')
  })

  it('creates a backend-backed guest session', async () => {
    const res = await apiClient.post('/auth/guest-login')
    expect(res.status).toBe(201)
    expect(res.data.user.role).toBe('guest')
    expect(res.data.tokens.access.token).toBeTruthy()
  })

  it('rejects invalid credentials', async () => {
    try {
      await apiClient.post('/auth/login', {
        email: 'pavan@bellcorpstudio.com',
        password: 'wrongpassword',
      })
      expect.fail('should have thrown')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status: number } }
      expect(axiosErr.response?.status).toBe(400)
    }
  })

  it('signs up a new user', async () => {
    const res = await apiClient.post('/auth/register', {
      name: 'New User',
      email: 'newuser@test.com',
      password: 'password123',
    })
    expect(res.data.user.name).toBe('New User')
    expect(res.status).toBe(201)
  })

  it('rejects duplicate email on signup', async () => {
    try {
      await apiClient.post('/auth/register', {
        name: 'Pavan Kumar',
        email: 'pavan@bellcorpstudio.com',
        password: 'password123',
      })
      expect.fail('should have thrown')
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status: number } }
      expect(axiosErr.response?.status).toBe(400)
    }
  })
})
