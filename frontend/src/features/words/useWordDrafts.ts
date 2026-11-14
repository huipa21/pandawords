import type { OverrideFields } from './dictionaryView'
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'

export const useWordDrafts = defineStore('word-detail-drafts', () => {
  const auth = useAuthStore()
  const overrides = ref<Record<string, OverrideFields>>({})
  const notes = ref<Record<string, string>>({})
  watch(() => auth.user?.id, () => {
    overrides.value = {}
    notes.value = {}
  })
  return { overrides, notes }
})
