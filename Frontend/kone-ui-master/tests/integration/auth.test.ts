import { describe, it, expect } from 'vitest'
import { authService } from '../../src/services/auth.service'

describe('auth service (integration with MSW)', () => {
  it('logs in with valid credentials', async () => {
    const result = await authService.login({ email: 'admin@kone.com', password: 'password123' })
    expect(result.user.email).toBe('admin@kone.com')
    expect(result.token).toMatch(/^mock-token-/)
  })

  it('throws on invalid credentials', async () => {
    await expect(
      authService.login({ email: 'admin@kone.com', password: 'wrong' })
    ).rejects.toBeDefined()
  })
})
