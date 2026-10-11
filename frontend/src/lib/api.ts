import { getCurrentDemoUser } from '@/store/sessionStore'

export const apiFetch = (input: RequestInfo | URL, init: RequestInit = {}) => {
  const headers = new Headers(init.headers)
  headers.set('X-Demo-Role', getCurrentDemoUser().role)
  return fetch(input, { ...init, headers })
}
