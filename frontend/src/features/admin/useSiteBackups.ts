import type { components } from '@/api/schema'
import { onScopeDispose, ref, shallowRef } from 'vue'
import { api } from '@/api/client'
import { usePortabilityI18n } from '@/features/portability/messages'
import { useArchiveDownload } from '@/features/portability/useArchiveDownload'
import { useProjectErrors } from '@/features/projects/useProject'

export type SiteBackupStatus = components['schemas']['SiteBackupStatus']
export const POLL_MS = 3000

/** Admin site-backup status with polling while a backup runs; downloads go through the authenticated client. */
export function useSiteBackups() {
  const { t } = usePortabilityI18n()
  const errorText = useProjectErrors()
  const status = shallowRef<SiteBackupStatus>()
  const loading = ref(false)
  const starting = ref(false)
  const loadError = ref('')
  const actionError = ref('')
  const downloading = ref('')
  const processing = ref<'' | 'download' | 'delete'>('')
  const archive = useArchiveDownload('site.tar.gz')
  let timer: ReturnType<typeof setTimeout> | undefined
  let request = 0
  let disposed = false
  let cancelled = false

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
    return ok
  }

  function cancelDownload() {
    cancelled = true
    archive.cancel()
  }

  async function downloadSelected(names: string[]) {
    if (processing.value)
      return
    processing.value = 'download'
    cancelled = false
    try {
      for (const name of names) {
        if (cancelled || disposed || !await download(name))
          break
      }
    }
    finally {
      processing.value = ''
    }
  }

  async function deleteSelected(names: string[]) {
    if (processing.value)
      return false
    processing.value = 'delete'
    actionError.value = ''
    try {
      for (const name of names) {
        if (disposed)
          return false
        const result = await api.DELETE('/api/admin/backups/{name}', {
          params: {
            path: { name },
          },
        })
        if (!result.response.ok) {
          actionError.value = errorText(result.error, result.response.status)
          return false
        }
        if (status.value) {
          status.value = {
            ...status.value,
            backups: status.value.backups.filter(backup => backup.name !== name),
          }
        }
      }
      return true
    }
    catch {
      if (!disposed)
        actionError.value = t('errors.transport')
      return false
    }
    finally {
      processing.value = ''
    }
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
    processing,
    load,
    start,
    download,
    downloadSelected,
    deleteSelected,
    cancelDownload,
  }
}
