import { create } from 'zustand'
import apiClient from '../api/client'
import { initials } from '../lib/utils'
import type { User } from '../types'

interface AuthTokens {
  access: { token: string; expires: string }
  refresh: { token: string; expires: string }
}

interface AuthState {
  user: User | null
  isAuthenticated: boolean
  isGuest: boolean
  token: string | null
  signIn: (email: string, password: string) => Promise<void>
  signUp: (name: string, email: string, password: string) => Promise<void>
  continueAsGuest: () => Promise<void>
  signOut: () => void
  hydrate: () => void
}

function mapApiUser(apiUser: { id: string; name: string; email: string; role?: string; company?: string; avatarInitials?: string }): User {
  return {
    id: apiUser.id,
    email: apiUser.email,
    name: apiUser.name,
    role: apiUser.role === 'guest' ? 'guest' : 'authenticated',
    company: apiUser.company ?? 'KONE',
    avatarInitials: apiUser.avatarInitials ?? initials(apiUser.name),
  }
}

export const useAuthStore = create<AuthState>()(set => ({
  user: null,
  isAuthenticated: false,
  isGuest: false,
  token: null,

  signIn: async (email, password) => {
    const { data } = await apiClient.post<{ user: { id: string; name: string; email: string; role?: string }; tokens: AuthTokens }>('/auth/login', {
      email,
      password,
    })
    const user = mapApiUser(data.user)
    const accessToken = data.tokens.access.token
    const refreshToken = data.tokens.refresh.token
    localStorage.setItem('salesnxt_token', accessToken)
    localStorage.setItem('salesnxt_refresh_token', refreshToken)
    localStorage.setItem('salesnxt_user', JSON.stringify(user))
    set({ user, token: accessToken, isAuthenticated: true, isGuest: false })
  },

  signUp: async (name, email, password) => {
    const { data } = await apiClient.post<{ user: { id: string; name: string; email: string; role?: string }; tokens: AuthTokens }>('/auth/register', {
      name,
      email,
      password,
    })
    const user = mapApiUser(data.user)
    const accessToken = data.tokens.access.token
    const refreshToken = data.tokens.refresh.token
    localStorage.setItem('salesnxt_token', accessToken)
    localStorage.setItem('salesnxt_refresh_token', refreshToken)
    localStorage.setItem('salesnxt_user', JSON.stringify(user))
    set({ user, token: accessToken, isAuthenticated: true, isGuest: false })
  },

  continueAsGuest: async () => {
    const { data } = await apiClient.post<{ user: { id: string; name: string; email: string; role?: string }; tokens: AuthTokens }>('/auth/guest-login')
    const user = mapApiUser(data.user)
    const accessToken = data.tokens.access.token
    const refreshToken = data.tokens.refresh.token
    localStorage.setItem('salesnxt_token', accessToken)
    localStorage.setItem('salesnxt_refresh_token', refreshToken)
    localStorage.setItem('salesnxt_user', JSON.stringify(user))
    set({ user, token: accessToken, isAuthenticated: true, isGuest: true })
  },

  signOut: () => {
    const refreshToken = localStorage.getItem('salesnxt_refresh_token')
    if (refreshToken) {
      apiClient.post('/auth/logout', { refreshToken }).catch(() => {})
    }
    localStorage.removeItem('salesnxt_token')
    localStorage.removeItem('salesnxt_refresh_token')
    localStorage.removeItem('salesnxt_user')
    set({ user: null, isAuthenticated: false, isGuest: false, token: null })
  },

  hydrate: () => {
    const token = localStorage.getItem('salesnxt_token')
    const userStr = localStorage.getItem('salesnxt_user')
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr) as User
        set({ user, token, isAuthenticated: true, isGuest: user.role === 'guest' })
        return
      } catch {
        localStorage.removeItem('salesnxt_token')
        localStorage.removeItem('salesnxt_refresh_token')
        localStorage.removeItem('salesnxt_user')
      }
    }
  },
}))
