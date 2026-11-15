import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createApiClient } from '@/api/client'
import { authPayload } from '@/features/auth/testHarness'
import { activateOfflineOwner, offlineData } from '@/features/study/offlineStorage'
import { useAuthStore } from './auth'
import 'fake-indexeddb/auto'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

describe('memory-only auth store', () => {
  it('retains offline answers across a transient refresh outage but deletes them on explicit logout', async () => {
    let disconnected = false
    vi.stubGlobal('fetch', vi.fn<typeof globalThis.fetch>(async (input, init) => {
      if (disconnected)
        throw new Error('network lost')
      return new Request(input, init).url.endsWith('/logout')
        ? new Response(null, { status: 204 })
        : Response.json(authPayload())
    }))
    const auth = useAuthStore()
    await auth.login({ username: 'learner', password: 'password-for-test' })
    const owner = auth.user!.id
    await offlineData(owner, (data) => {
      data.entries = [
        {
          attempt: {
            id: 'preserved',
            project_id: 'project',
            prompt: { text: 'Prompt', input: 'text', choices: [] },
            exercise: 'cloze',
            issued_at: '2026-01-01T00:00:00Z',
            expires_at: '2099-01-01T00:00:00Z',
          },
          answer: { answer: 'saved', duration_ms: 10, client_key: 'stable-retry-key' },
        },
      ]
    })
    disconnected = true
    await auth.refresh()
    expect(auth.user).toBeNull()
    await expect(offlineData(owner)).rejects.toThrow()
    disconnected = false
    await auth.refresh()
    expect((await offlineData(owner)).entries[0]!.answer!.answer).toBe('saved')
    await auth.logout()
    activateOfflineOwner(owner)
    expect((await offlineData(owner)).entries).toEqual([])
  })
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

  it('refreshes an expired logout bearer independently, revokes its rotated cookie, and cannot overwrite a queued login', async () => {
    const refreshed = deferred<Response>()
    const calls: string[] = []
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const request = new Request(input, init)
      const path = new URL(request.url).pathname
      const bearer = request.headers.get('Authorization')
      calls.push(`${path}:${bearer}`)
      if (path.endsWith('/refresh'))
        return refreshed.promise
      if (path.endsWith('/logout')) {
        return new Response(null, {
          status: bearer === 'Bearer rotated-access'
            ? 204
            : 401,
        })
      }
      return Response.json({
        ...authPayload(),
        access_token: calls.length === 1
          ? 'expired-access'
          : 'new-login-access',
      })
    })
    vi.stubGlobal('fetch', fetch)
    const auth = useAuthStore()
    await auth.login({ username: 'learner', password: 'old-password' })
    const logout = auth.logout()
    const outcome = logout.then(() => null, error => error)
    await vi.waitFor(() => expect(calls).toContain('/api/auth/logout:Bearer expired-access'))
    const login = auth.login({ username: 'learner', password: 'new-password' })
    refreshed.resolve(Response.json({
      ...authPayload(),
      access_token: 'rotated-access',
    }))
    expect(await outcome).toBeNull()
    await login
    expect(calls).toEqual([
      '/api/auth/login:null',
      '/api/auth/logout:Bearer expired-access',
      '/api/auth/refresh:null',
      '/api/auth/logout:Bearer rotated-access',
      '/api/auth/login:null',
    ])
    expect(auth.accessToken).toBe('new-login-access')
    expect(auth.user?.username).toBe('learner')
  })

  it.each([401, 403, 503, 'transport'] as const)('handles expired logout refresh failure %s without hiding server/transport errors', async (failure) => {
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      if (new Request(input, init).url.endsWith('/logout'))
        return new Response(null, { status: 401 })
      if (failure === 'transport')
        throw new Error('offline')
      return new Response(null, { status: failure })
    })
    vi.stubGlobal('fetch', fetch)
    const auth = useAuthStore()
    const logout = auth.logout()
    if (failure === 401 || failure === 403) {
      await expect(logout).resolves.toBeUndefined()
    }
    else {
      await expect(logout).rejects.toMatchObject({
        error: {
          code: failure === 'transport'
            ? 'transport'
            : 'http.503',
        },
      })
    }
    expect(auth.accessToken).toBeNull()
    expect(auth.user).toBeNull()
    expect(fetch).toHaveBeenCalledTimes(2)
  })
})
