import { onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useProjectErrors } from '@/features/projects/useProject'

export function useStudyResource<T>(
  key: () => string,
  fetcher: (key: string) => Promise<{ data?: T, error?: unknown, response: Response }>,
) {
  const { t } = useI18n()
  const errorText = useProjectErrors()
  const data = shallowRef<T>()
  const loading = ref(false)
  const error = ref('')
  let generation = 0

  async function load() {
    const current = ++generation
    data.value = undefined
    loading.value = true
    error.value = ''
    try {
      const result = await fetcher(key())
      if (current !== generation)
        return
      if (result.data)
        data.value = result.data
      else
        error.value = errorText(result.error, result.response.status)
    }
    catch {
      if (current === generation)
        error.value = t('errors.transport')
    }
    finally {
      if (current === generation)
        loading.value = false
    }
  }
  watch(key, load, { immediate: true })
  onScopeDispose(() => generation++)
  return { data, loading, error, load }
}
