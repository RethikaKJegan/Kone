import { create } from 'zustand'
import apiClient from '../api/client'
import { clearGuestSessionId } from '../api/guestWorkflow'
import { GUEST_USER } from '../lib/constants'
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
  guestBannerDismissed: boolean
  signIn: (email: string, password: string) => Promise<void>
  signUp: (name: string, email: string, password: string) => Promise<void>
  continueAsGuest: () => void
  signOut: () => void
  hydrate: () => void
  dismissGuestBanner: () => void
  resetGuestBanner: () => void
}

function mapApiUser(apiUser: { id: string; name: string; email: string; role?: string; company?: string; avatarInitials?: string }): User {
  return {
    id: apiUser.id,
    email: apiUser.email,
    name: apiUser.name,
    role: 'authenticated',
    company: apiUser.company ?? 'KONE',
    avatarInitials: apiUser.avatarInitials ?? initials(apiUser.name),
  }
}

export const useAuthStore = create<AuthState>()((set, get) => ({
  user: null,
  isAuthenticated: false,
  isGuest: false,
  token: null,
  guestBannerDismissed: false,

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
    sessionStorage.removeItem('guest_session')
    clearGuestSessionId()
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
    sessionStorage.removeItem('guest_session')
    clearGuestSessionId()
    set({ user, token: accessToken, isAuthenticated: true, isGuest: false })
  },

  continueAsGuest: () => {
    sessionStorage.setItem('guest_session', '1')
    set({ user: GUEST_USER, isGuest: true, isAuthenticated: false, token: null })
  },

  signOut: () => {
    const refreshToken = localStorage.getItem('salesnxt_refresh_token')
    if (refreshToken) {
      apiClient.post('/auth/logout', { refreshToken }).catch(() => {})
    }
    localStorage.removeItem('salesnxt_token')
    localStorage.removeItem('salesnxt_refresh_token')
    localStorage.removeItem('salesnxt_user')
    sessionStorage.removeItem('guest_session')
    sessionStorage.removeItem('guest_projects')
    sessionStorage.removeItem('guest_offerings')
    clearGuestSessionId()
    set({ user: null, isAuthenticated: false, isGuest: false, token: null })
  },

  hydrate: () => {
    const token = localStorage.getItem('salesnxt_token')
    const userStr = localStorage.getItem('salesnxt_user')
    if (token && userStr) {
      try {
        const user = JSON.parse(userStr) as User
        set({ user, token, isAuthenticated: true, isGuest: false })
        return
      } catch {
        localStorage.removeItem('salesnxt_token')
        localStorage.removeItem('salesnxt_refresh_token')
        localStorage.removeItem('salesnxt_user')
      }
    }
    if (sessionStorage.getItem('guest_session') === '1') {
      set({ user: GUEST_USER, isGuest: true, isAuthenticated: false, token: null })
    }
  },

  dismissGuestBanner: () => set({ guestBannerDismissed: true }),
  resetGuestBanner: () => {
    if (get().isGuest) set({ guestBannerDismissed: false })
  },
}))
