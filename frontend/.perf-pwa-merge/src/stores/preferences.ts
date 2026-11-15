import { defineStore } from 'pinia'
import { computed, onScopeDispose, ref, watch } from 'vue'

export type ThemePreference = 'system' | 'light' | 'dark'
export type LocalePreference = 'zh-CN' | 'en'

export const preferencesKey = 'pandawords.preferences'

function readPreferences(): { theme?: unknown, locale?: unknown } {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(preferencesKey) ?? '{}')
    return saved && typeof saved === 'object'
      ? saved
      : {}
  }
  catch {
    return {}
  }
}

export const usePreferencesStore = defineStore('preferences', () => {
  const saved = readPreferences()
  const theme = ref<ThemePreference>(
    saved.theme === 'light' || saved.theme === 'dark'
      ? saved.theme
      : 'system',
  )
  const locale = ref<LocalePreference>(saved.locale === 'en'
    ? 'en'
    : 'zh-CN')
  const media = window.matchMedia?.('(prefers-color-scheme: dark)')
  const systemDark = ref(media?.matches ?? false)
  const resolvedTheme = computed(() => theme.value === 'system'
    ? (systemDark.value ? 'dark' : 'light')
    : theme.value)

  function followSystem(event: MediaQueryListEvent) {
    systemDark.value = event.matches
  }
  media?.addEventListener('change', followSystem)
  onScopeDispose(() => media?.removeEventListener('change', followSystem))

  watch([theme, locale], () => {
    try {
      localStorage.setItem(preferencesKey, JSON.stringify({ theme: theme.value, locale: locale.value }))
    }
    catch {
      // Preferences still work when browser storage is unavailable.
    }
  }, { flush: 'sync' })

  return { theme, locale, resolvedTheme }
})
