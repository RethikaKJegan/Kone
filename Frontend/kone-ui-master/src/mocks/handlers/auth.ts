import { http, HttpResponse, delay } from 'msw'
import { users, tokens, SEEDED_USER } from '../data/seed'
import { generateId, initials } from '../../lib/utils'
import type { User } from '../../types'

function makeTokenPair(userId: string) {
  const accessToken = generateId()
  const refreshToken = generateId()
  tokens.set(accessToken, userId)
  return {
    access: { token: accessToken, expires: new Date(Date.now() + 30 * 60 * 1000).toISOString() },
    refresh: { token: refreshToken, expires: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() },
  }
}

export const authHandlers = [
  http.post('/api/v1/auth/login', async ({ request }) => {
    await delay(600)
    const body = (await request.json()) as { email: string; password: string }

    const userRecord = users.get(body.email)
    const isKoneEmail = body.email.endsWith('@kone.com') && body.password.length > 0

    if (!userRecord && !isKoneEmail) {
      return HttpResponse.json({ code: 400, message: 'Incorrect email or password' }, { status: 400 })
    }

    if (userRecord && userRecord.password !== body.password) {
      return HttpResponse.json({ code: 400, message: 'Incorrect email or password' }, { status: 400 })
    }

    let user: User
    if (userRecord) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { password: _p, ...rest } = userRecord
      user = rest
    } else {
      const namePart = body.email.split('@')[0].replace('.', ' ')
      const name = namePart.charAt(0).toUpperCase() + namePart.slice(1)
      user = {
        id: `user-${generateId()}`,
        email: body.email,
        name,
        role: 'authenticated',
        company: 'KONE',
        avatarInitials: initials(name),
      }
    }

    const mockTokens = makeTokenPair(user.id)

    return HttpResponse.json({ user, tokens: mockTokens })
  }),

  http.post('/api/v1/auth/register', async ({ request }) => {
    await delay(700)
    const body = (await request.json()) as { name: string; email: string; password: string }

    if (users.has(body.email)) {
      return HttpResponse.json(
        { code: 400, message: 'Email already taken' },
        { status: 400 }
      )
    }

    if (body.password.length < 8) {
      return HttpResponse.json(
        { code: 400, message: 'Password must be at least 8 characters' },
        { status: 400 }
      )
    }

    const user: User = {
      id: `user-${generateId()}`,
      email: body.email,
      name: body.name,
      role: 'authenticated',
      company: 'KONE',
      avatarInitials: initials(body.name),
    }

    users.set(body.email, { ...user, password: body.password })
    const mockTokens = makeTokenPair(user.id)

    return HttpResponse.json({ user, tokens: mockTokens }, { status: 201 })
  }),

  http.post('/api/v1/auth/logout', async () => {
    await delay(200)
    return new HttpResponse(null, { status: 204 })
  }),

  http.get('/api/v1/auth/me', async ({ request }) => {
    const auth = request.headers.get('Authorization')
    if (!auth?.startsWith('Bearer ')) {
      return HttpResponse.json({ code: 401, message: 'Unauthorized' }, { status: 401 })
    }
    const token = auth.slice(7)
    const userId = tokens.get(token)
    if (!userId) return HttpResponse.json({ code: 401, message: 'Unauthorized' }, { status: 401 })
    if (userId === SEEDED_USER.id) return HttpResponse.json(SEEDED_USER)
    const user = [...users.values()].find(u => u.id === userId)
    if (!user) return HttpResponse.json({ code: 404, message: 'Not found' }, { status: 404 })
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { password: _p, ...rest } = user
    return HttpResponse.json(rest)
  }),
]
