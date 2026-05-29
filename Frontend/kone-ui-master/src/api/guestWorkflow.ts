import apiClient from './client'

const GUEST_SESSION_KEY = 'guest_session_id'

export function isGuestSession() {
  return sessionStorage.getItem('guest_session') === '1'
}

export async function getGuestSessionId() {
  const existing = localStorage.getItem(GUEST_SESSION_KEY)
  if (existing) return existing

  const { data } = await apiClient.post<{ session_id: string }>('/guest/session')
  localStorage.setItem(GUEST_SESSION_KEY, data.session_id)
  return data.session_id
}

export function clearGuestSessionId() {
  localStorage.removeItem(GUEST_SESSION_KEY)
}

export function getGuestPayload(projectId: string, projectName: string) {
  const sessionId = localStorage.getItem(GUEST_SESSION_KEY)
  if (!sessionId) throw new Error('Guest session not initialized')
  return {
    is_guest: true,
    session_id: sessionId,
    project_id: projectId,
    project_name: projectName,
  }
}
