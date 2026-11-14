import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApiClient } from '@/api/client'
import { authPayload } from '@/features/auth/testHarness'
import { useAuthStore } from './auth'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('memory-only auth store', () => {
  let pinia: ReturnType<typeof createPinia>
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
    localStorage.clear()
    sessionStorage.clear()
  })
  afterEach(() => {
    disposePinia(pinia)
    vi.unstubAllGlobals()
  })

  it('uses login credentials for password change and applies fresh usable credentials', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const request = new Request(input, init)
      if (request.url.endsWith('/password')) {
        expect(request.headers.get('Authorization')).toBe('Bearer test-access')
        return Response.json({
          ...authPayload(),
          access_token: 'fresh-access',
        })
      }
      return Response.json(authPayload({ must_change_password: true }))
    })
    vi.stubGlobal('fetch', fetch)
    const auth = useAuthStore()
    await auth.login({ username: 'learner', password: 'temporary-password' })
    expect(auth.user?.must_change_password).toBe(true)
    await auth.changePassword({ current_password: 'temporary-password', new_password: 'new-password' })
    expect(auth.accessToken).toBe('fresh-access')
    expect(auth.user?.must_change_password).toBe(false)
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('prevents concurrent recovery from resurrecting a logged-out or newer session and orders cookie mutations', async () => {
    const pending = deferred<Response>()
    const calls: string[] = []
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const request = new Request(input, init)
      const path = new URL(request.url).pathname
      calls.push(path)
      if (path === '/api/auth/refresh')
        return pending.promise
      if (path === '/api/auth/logout') {
        expect(request.headers.get('Authorization')).toBe('Bearer stale-access')
        return new Response(null, { status: 204 })
      }
      if (path === '/api/auth/login') {
        return Response.json({
          ...authPayload(),
          access_token: calls.length === 1
            ? 'old-access'
            : 'new-access',
        })
      }
      return new Response(null, { status: 401 })
    })
    vi.stubGlobal('fetch', fetch)
    const auth = useAuthStore()
    await auth.login({ username: 'learner', password: 'old-password' })
    const reset = vi.spyOn(auth, 'reset')
    const client = createApiClient({
      baseUrl: 'https://pandawords.test',
      auth: {
        getAccessToken: () => auth.accessToken,
        getSessionVersion: auth.getSessionVersion,
        refresh: auth.refresh,
        logout: reset,
      },
    })
    const requests = Promise.all([
      client.GET('/api/healthz'),
      client.GET('/api/readyz'),
    ])
    await vi.waitFor(() => expect(calls.filter(path => path.endsWith('/refresh'))).toHaveLength(1))
    const logout = auth.logout()
    expect(auth.accessToken).toBeNull()
    const login = auth.login({ username: 'learner', password: 'new-password' })
    expect(calls).not.toContain('/api/auth/logout')
    pending.resolve(Response.json({
      ...authPayload(),
      access_token: 'stale-access',
    }))
    await Promise.all([requests, logout, login])
    expect(auth.accessToken).toBe('new-access')
    expect(reset).not.toHaveBeenCalled()
    expect(calls.slice(-2)).toEqual(['/api/auth/logout', '/api/auth/login'])
    expect(calls.filter(path => path.endsWith('/healthz'))).toHaveLength(1)
    expect(calls.filter(path => path.endsWith('/readyz'))).toHaveLength(1)
  })

  it('shows transport/server restore failures while deliberately clearing the session', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    const auth = useAuthStore()
    await auth.restore()
    expect(auth.sessionError).toBe('transport')
    expect(auth.accessToken).toBeNull()
  })

  it('preserves a backend field error instead of silently swallowing password failures', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({
      code: 'auth.invalid_credentials',
      field: 'current_password',
      message: 'Incorrect',
    }, { status: 401 })))
    await expect(useAuthStore().changePassword({
      current_password: 'wrong',
      new_password: 'new-password',
    })).rejects.toMatchObject({
      error: { code: 'auth.invalid_credentials', field: 'current_password' },
    })
  })
})
