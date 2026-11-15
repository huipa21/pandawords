import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { preferencesKey, usePreferencesStore } from './preferences'

describe('preferences', () => {
  let media: EventTarget & { matches: boolean }
  let pinia: ReturnType<typeof createPinia>

  beforeEach(() => {
    localStorage.clear()
    media = Object.assign(new EventTarget(), { matches: false })
    vi.stubGlobal('matchMedia', vi.fn(() => media))
    pinia = createPinia()
    setActivePinia(pinia)
  })

  afterEach(() => {
    disposePinia(pinia)
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  function systemChange(matches: boolean) {
    media.matches = matches
    media.dispatchEvent(Object.assign(new Event('change'), { matches }))
  }

  it('uses only explicit light/dark choices and ignores system changes', () => {
    const store = usePreferencesStore()
    expect(store.theme).toBe('light')
    expect(store.resolvedTheme).toBe('light')
    systemChange(true)
    expect(store.resolvedTheme).toBe('light')
    store.theme = 'dark'
    systemChange(false)
    expect(store.resolvedTheme).toBe('dark')
    expect(store.theme).toBe('dark')
  })

  it('restores persisted choices and persists both preferences', () => {
    localStorage.setItem(preferencesKey, JSON.stringify({ theme: 'dark', locale: 'en' }))
    const store = usePreferencesStore()
    expect(store.resolvedTheme).toBe('dark')
    expect(store.locale).toBe('en')
    store.theme = 'light'
    store.locale = 'zh-CN'
    expect(JSON.parse(localStorage.getItem(preferencesKey)!)).toEqual({ theme: 'light', locale: 'zh-CN' })
  })

  it.each([
    'null',
    '{broken',
    '{"theme":"invalid","locale":"invalid"}',
    '{"theme":"system","locale":"zh-CN"}',
  ])('uses light for invalid or legacy system preferences: %s', (value) => {
    localStorage.setItem(preferencesKey, value)
    media.matches = true
    const store = usePreferencesStore()
    expect(store.theme).toBe('light')
    expect(store.locale).toBe('zh-CN')
    expect(store.resolvedTheme).toBe('light')
  })

  it('keeps preferences usable when storage reads and writes fail', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Storage unavailable')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Storage unavailable')
    })
    const store = usePreferencesStore()
    expect(store.locale).toBe('zh-CN')
    expect(() => {
      store.theme = 'dark'
      store.locale = 'en'
    }).not.toThrow()
    expect(store.resolvedTheme).toBe('dark')
    expect(store.locale).toBe('en')
  })
})
