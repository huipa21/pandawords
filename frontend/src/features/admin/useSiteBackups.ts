import type { components } from '@/api/schema'
import { onScopeDispose, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { useArchiveDownload } from '@/features/portability/useArchiveDownload'
import { useProjectErrors } from '@/features/projects/useProject'

export type SiteBackupStatus = components['schemas']['SiteBackupStatus']
export const POLL_MS = 3000

/** Admin site-backup status with polling while a backup runs; downloads go through the authenticated client. */
export function useSiteBackups() {
  const { t } = useI18n()
  const errorText = useProjectErrors()
  const status = shallowRef<SiteBackupStatus>()
  const loading = ref(false)
  const starting = ref(false)
  const loadError = ref('')
  const actionError = ref('')
  const downloading = ref('')
  const archive = useArchiveDownload('site.tar.gz')
  let timer: ReturnType<typeof setTimeout> | undefined
  let request = 0
  let disposed = false

  function schedule() {
    clearTimeout(timer)
    timer = undefined
    if (!disposed && status.value?.running)
      timer = setTimeout(() => void load(), POLL_MS)
  }

  async function load() {
    const current = ++request
    loading.value = true
    try {
      const result = await api.GET('/api/admin/backups')
      if (current !== request || disposed)
        return
      if (result.data) {
        status.value = result.data
        loadError.value = ''
      }
      else {
        loadError.value = errorText(result.error, result.response.status)
      }
    }
    catch {
      if (current === request && !disposed)
        loadError.value = t('errors.transport')
    }
    finally {
      if (current === request && !disposed) {
        loading.value = false
        schedule()
      }
    }
  }

  async function start() {
    if (starting.value || status.value?.running)
      return
    starting.value = true
    actionError.value = ''
    try {
      const result = await api.POST('/api/admin/backups')
      if (disposed)
        return
      if (result.data) {
        request++
        loading.value = false
        status.value = result.data
        schedule()
      }
      else {
        actionError.value = errorText(result.error, result.response.status)
        if (result.response.status === 409)
          void load()
      }
    }
    catch {
      if (!disposed)
        actionError.value = t('errors.transport')
    }
    finally {
      starting.value = false
    }
  }

  async function download(name: string) {
    downloading.value = name
    actionError.value = ''
    const ok = await archive.download(signal => api.GET('/api/admin/backups/{name}', {
      params: {
        path: { name },
      },
      parseAs: 'blob',
      signal,
    }))
    if (!ok && archive.error.value)
      actionError.value = archive.error.value.text
    downloading.value = ''
  }

  function cancelDownload() {
    archive.cancel()
    downloading.value = ''
  }

  onScopeDispose(() => {
    disposed = true
    request++
    clearTimeout(timer)
  })
  return {
    status,
    loading,
    starting,
    loadError,
    actionError,
    downloading,
    load,
    start,
    download,
    cancelDownload,
  }
}
