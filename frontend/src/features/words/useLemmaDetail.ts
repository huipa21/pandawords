import type { DictionaryEntry, DictionaryRecord, Override, OverrideFields } from './dictionaryView'
import { useMessage } from 'naive-ui'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { normalizeApiError } from '@/api/errors'
import { entryRecords } from './dictionaryView'

export function useWordErrors() {
  const { t, te } = useI18n()
  return (error: unknown, status: number) => {
    const key = `errors.${normalizeApiError(error, status).code.replaceAll('.', '_')}`
    return status === 404
      ? t('lemmaDetail.unavailable')
      : t(te(key)
          ? key
          : 'errors.generic')
  }
}

export function useLemmaDetail(id: () => string) {
  const { t } = useI18n()
  const message = useMessage()
  const errorText = useWordErrors()
  const entry = ref<DictionaryEntry>()
  const overrides = ref<Record<string, Override>>({})
  const loading = ref(false)
  const busy = ref(false)
  const loadError = ref('')
  const fieldError = ref('')
  let generation = 0
  let disposed = false

  async function load() {
    const current = ++generation
    let failure = ''
    loading.value = true
    loadError.value = ''
    try {
      const result = await api.GET('/api/dictionary/lemmas/{lemma_id}/entry', {
        params: {
          path: {
            lemma_id: id(),
          },
        },
      })
      if (!result.data) {
        failure = errorText(result.error, result.response.status)
        throw new Error(failure)
      }
      if (disposed || current !== generation)
        return
      const effective = result.data
      const own = await Promise.all(entryRecords(effective).map(async (record) => {
        const result = await api.GET('/api/dictionary/{table}/{id}/override', {
          params: {
            path: { table: record.table, id: record.id },
          },
        })
        if (!result.data && result.response.status !== 404) {
          failure = errorText(result.error, result.response.status)
          throw new Error(failure)
        }
        return result.data
      }))
      if (disposed || current !== generation)
        return
      entry.value = effective
      overrides.value = Object.fromEntries(own.filter(value => value !== undefined).map(value => [value.target_id, value]))
    }
    catch {
      if (!disposed && current === generation)
        loadError.value = failure || t('errors.transport')
    }
    finally {
      if (!disposed && current === generation)
        loading.value = false
    }
  }

  async function mutate(record: DictionaryRecord, fields?: OverrideFields) {
    if (busy.value)
      return false
    const current = generation
    busy.value = true
    fieldError.value = ''
    try {
      const params = {
        path: { table: record.table, id: record.id },
      }
      const result = fields
        ? await api.PATCH('/api/dictionary/{table}/{id}/override', {
            params,
            body: { fields },
          })
        : await api.DELETE('/api/dictionary/{table}/{id}/override', { params })
      if (disposed || current !== generation)
        return false
      if (!result.response.ok) {
        const error = normalizeApiError(result.error, result.response.status)
        const text = errorText(error, result.response.status)
        if (error.field)
          fieldError.value = text
        else
          message.error(text)
        return false
      }
      message.success(t('lemmaDetail.saved'), { duration: 2000 })
      await load()
      return true
    }
    catch {
      if (!disposed && current === generation)
        message.error(t('errors.transport'))
      return false
    }
    finally {
      busy.value = false
    }
  }

  watch(id, () => {
    entry.value = undefined
    overrides.value = {}
    fieldError.value = ''
    void load()
  }, { immediate: true })
  onScopeDispose(() => {
    disposed = true
    generation++
  })
  return {
    entry,
    overrides,
    loading,
    busy,
    loadError,
    fieldError,
    load,
    mutate,
  }
}
