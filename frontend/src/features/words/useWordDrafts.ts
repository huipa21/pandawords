import type { OverrideFields } from './dictionaryView'
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

export const useWordDrafts = defineStore('word-detail-drafts', () => {
  const auth = useAuthStore()
  const overrides = ref<Record<string, OverrideFields>>({})
  const notes = ref<Record<string, string>>({})
  const storageKey = () => auth.user?.id
    ? `pw:word-notes:${auth.user.id}`
    : undefined
  watch(() => auth.user?.id, () => {
    overrides.value = {}
    let restored: Record<string, string> = {}
    try {
      const key = storageKey()
      const parsed: unknown = key
        ? JSON.parse(sessionStorage.getItem(key) ?? '{}')
        : {}
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        restored = Object.fromEntries(Object.entries(parsed).filter(([, value]) => typeof value === 'string'))
      }
    }
    catch { /* Storage is optional; in-memory editing still works. */ }
    notes.value = restored
  }, { immediate: true, flush: 'sync' })
  watch(notes, (value) => {
    try {
      const key = storageKey()
      if (key)
        sessionStorage.setItem(key, JSON.stringify(value))
    }
    catch { /* Retain the in-memory draft if browser storage is unavailable. */ }
  }, { deep: true, flush: 'sync' })
  return { overrides, notes }
})
