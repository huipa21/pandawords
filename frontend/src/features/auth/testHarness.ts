import type { components } from '@/api/schema'
import { vi } from 'vitest'

export function authPayload(overrides: Partial<components['schemas']['UserRead']> = {}): components['schemas']['AuthRead'] {
  return {
    access_token: 'test-access',
    token_type: 'bearer',
    user: {
      id: 'user:test',
      username: 'learner',
      role: 'user',
      disabled: false,
      must_change_password: false,
      source_lang: 'zh',
      target_lang: 'en',
      prefs: { theme: 'system', locale: 'zh-CN', accent: 'US' },
      ...overrides,
    },
  }
}

export function mockSession(overrides: Partial<components['schemas']['UserRead']> = {}) {
  const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json(authPayload(overrides)))
  vi.stubGlobal('fetch', fetch)
  return fetch
}
