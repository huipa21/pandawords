import type { components } from '@/api/schema'
import { useMessage } from 'naive-ui'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { normalizeApiError } from '@/api/errors'

export type Project = components['schemas']['ProjectRead']
export type ProjectCreate = components['schemas']['ProjectCreate']

export function useProjectErrors() {
  const { t, te } = useI18n()
  return (error: unknown, status: number) => {
    const key = `errors.${normalizeApiError(error, status).code.replaceAll('.', '_')}`
    return t(te(key)
      ? key
      : 'errors.generic')
  }
}

export function useProject(id: () => string | undefined) {
  const { t } = useI18n()
  const message = useMessage()
  const errorText = useProjectErrors()
  const project = ref<Project>()
  const loading = ref(false)
  const busy = ref(false)
  const loadError = ref('')
  const fields = ref<Record<string, string>>({})
  let request = 0
  let disposed = false

  async function load() {
    const current = ++request
    const rid = id()
    project.value = undefined
    loadError.value = ''
    fields.value = {}
    loading.value = false
    if (!rid)
      return
    loading.value = true
    try {
      const result = await api.GET('/api/projects/{id}', {
        params: {
          path: { id: rid },
        },
      })
      if (current !== request || disposed)
        return
      if (result.data)
        project.value = result.data
      else
        loadError.value = errorText(result.error, result.response.status)
    }
    catch {
      if (current === request && !disposed)
        loadError.value = t('errors.transport')
    }
    finally {
      if (current === request && !disposed)
        loading.value = false
    }
  }

  async function save(body: ProjectCreate) {
    if (busy.value)
      return
    busy.value = true
    fields.value = {}
    const rid = id()
    const current = request
    try {
      const result = rid
        ? await api.PATCH('/api/projects/{id}', {
            params: {
              path: { id: rid },
            },
            body,
          })
        : await api.POST('/api/projects', { body })
      if (disposed || current !== request)
        return
      if (result.data) {
        message.success(t('projects.saved'), { duration: 2000 })
        return result.data
      }
      const error = normalizeApiError(result.error, result.response.status)
      const text = errorText(error, result.response.status)
      if (error.field && [
        'name',
        'description',
        'target_lang',
        'source_lang',
        'plan.daily_new',
        'plan.review_cap',
        'plan.exam_date',
      ].includes(error.field)) {
        fields.value[error.field] = text
      }
      else {
        message.error(text)
      }
    }
    catch {
      if (!disposed && current === request)
        message.error(t('errors.transport'))
    }
    finally {
      busy.value = false
    }
  }

  watch(id, load, { immediate: true })
  onScopeDispose(() => {
    disposed = true
    request++
  })
  return {
    project,
    loading,
    busy,
    loadError,
    fields,
    load,
    save,
  }
}
