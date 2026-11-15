import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import { mockSession } from '@/features/auth/testHarness'
import { useAuthStore } from '@/stores/auth'
import { createAppRouter } from './router'

describe('auth route guards', () => {
  let pinia: ReturnType<typeof createPinia>
  beforeEach(() => {
    pinia = createPinia()
    setActivePinia(pinia)
  })
  afterEach(() => {
    disposePinia(pinia)
    vi.unstubAllGlobals()
  })

  it('restores once before navigation, protects design, and excludes admin routes for users', async () => {
    const fetch = mockSession()
    const router = createAppRouter(createMemoryHistory())
    await router.push('/dev/design')
    expect(router.currentRoute.value.name).toBe('design')
    for (const path of ['/reading', '/reading/opaque-passage']) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe('reading')
      expect(router.currentRoute.value.path).toBe(path)
    }
    for (const path of ['/admin/users', '/admin/backup', '/login']) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe('projects')
    }
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(new Request(fetch.mock.calls[0]![0]).credentials).toBe('include')
  })

  it('allows both admin routes after restoring an admin session', async () => {
    mockSession({ role: 'admin' })
    const router = createAppRouter(createMemoryHistory())
    for (const path of ['/admin/users', '/admin/backup']) {
      await router.push(path)
      expect(router.currentRoute.value.path).toBe(path)
    }
  })

  it('returns forced-change refresh to login with the localized error code, not a password-page loop', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({
      code: 'auth.password_change_required',
      message: 'Change required',
    }, { status: 403 }))
    vi.stubGlobal('fetch', fetch)
    const router = createAppRouter(createMemoryHistory())
    await router.push('/change-password')
    expect(router.currentRoute.value.name).toBe('login')
    expect(useAuthStore().sessionError).toBe('auth.password_change_required')
    await router.push('/dev/design')
    expect(router.currentRoute.value.name).toBe('login')
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('gates a logged-in temporary password user, including admin/design routes', async () => {
    mockSession({ must_change_password: true, role: 'admin' })
    const router = createAppRouter(createMemoryHistory())
    for (const path of [
      '/projects',
      '/profile',
      '/admin/users',
      '/dev/design',
      '/login',
    ]) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe('change-password')
    }
    await router.push('/change-password')
    expect(router.currentRoute.value.name).toBe('change-password')
  })

  it('rejects anonymous access without repeatedly restoring', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 401 }))
    vi.stubGlobal('fetch', fetch)
    const router = createAppRouter(createMemoryHistory())
    for (const path of [
      '/projects',
      '/profile',
      '/reading',
      '/reading/opaque-passage',
      '/admin/backup',
      '/dev/design',
      '/change-password',
    ]) {
      await router.push(path)
      expect(router.currentRoute.value.name).toBe('login')
    }
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(useAuthStore().sessionError).toBeNull()
  })
})
