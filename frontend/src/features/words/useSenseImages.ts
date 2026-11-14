import type { components } from '@/api/schema'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { normalizeApiError } from '@/api/errors'

export function useSenseImages(target: () => string) {
  const { t } = useI18n()
  const items = ref<components['schemas']['MediaRead'][]>([])
  const results = ref<components['schemas']['PixabaySearch']>()
  const busy = ref(false)
  const error = ref('')
  let generation = 0
  let disposed = false
  let pendingFile: File | undefined
  let uploadId = ''
  let selection: components['schemas']['ImageSelection'] | undefined
  let pendingQuery: string | undefined
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let wake: (() => void) | undefined

  function clear() {
    generation++
    controller?.abort()
    clearTimeout(timer)
    wake?.()
    pendingFile = undefined
    selection = undefined
    pendingQuery = undefined
    items.value = []
    results.value = undefined
    busy.value = false
    error.value = ''
  }
  async function load() {
    const result = await api.GET('/api/images/senses/{sense_id}', {
      params: {
        path: {
          sense_id: target(),
        },
      },
      signal: controller?.signal,
    })
    if (!result.data)
      throw new Error('unavailable')
    return result.data
  }
  async function run(action: () => Promise<void>) {
    if (busy.value)
      return
    busy.value = true
    error.value = ''
    const current = generation
    controller = new AbortController()
    try {
      await action()
      if (current === generation && !disposed) {
        const data = await load()
        if (current === generation && !disposed)
          items.value = data
      }
    }
    catch (failure) {
      if (current === generation && !disposed) {
        const code = failure instanceof Error
          ? failure.message
          : ''
        error.value = t(code === 'image.disabled'
          ? 'images.disabled'
          : code === 'image.rate_limit' || code === 'image.queue_full'
            ? 'images.rateLimit'
            : 'images.error')
      }
    }
    finally {
      if (current === generation && !disposed)
        busy.value = false
    }
  }
  async function refresh() {
    await run(async () => {})
  }
  async function upload(file?: File) {
    if (file) {
      pendingFile = file
      uploadId = crypto.randomUUID()
      selection = undefined
      pendingQuery = undefined
    }
    const chosen = pendingFile
    if (!chosen)
      return
    await run(async () => {
      const result = await api.POST('/api/images/senses/{sense_id}', {
        params: {
          path: {
            sense_id: target(),
          },
          header: { 'request-id': uploadId },
        },
        headers: { 'Content-Type': chosen.type },
        body: chosen.name,
        bodySerializer: () => chosen,
        signal: controller?.signal,
      })
      if (!result.data)
        throw new Error('upload')
      pendingFile = undefined
    })
  }
  async function search(q: string) {
    pendingQuery = q
    pendingFile = undefined
    selection = undefined
    const current = generation
    await run(async () => {
      const result = await api.GET('/api/images/pixabay/search', {
        params: {
          query: { q },
        },
        signal: controller?.signal,
      })
      if (!result.data)
        throw new Error(normalizeApiError(result.error, result.response.status).code)
      if (current === generation) {
        results.value = result.data
        pendingQuery = undefined
      }
    })
  }
  async function select(id?: number) {
    if (id !== undefined && results.value) {
      pendingQuery = undefined
      pendingFile = undefined
      selection = {
        request_id: crypto.randomUUID(),
        search_id: results.value.search_id,
        result_id: id,
      }
    }
    if (!selection)
      return
    const chosen = selection
    const current = generation
    await run(async () => {
      const result = await api.POST('/api/images/senses/{sense_id}/pixabay', {
        params: {
          path: {
            sense_id: target(),
          },
        },
        body: chosen,
        signal: controller?.signal,
      })
      if (!result.data)
        throw new Error(normalizeApiError(result.error, result.response.status).code)
      for (let count = 0; count < 90; count++) {
        const job = await api.GET('/api/jobs/{id}', {
          params: {
            path: { id: result.data.id },
          },
          signal: controller?.signal,
        })
        if (current !== generation || disposed)
          return
        if (!job.data || job.data.status === 'failed')
          throw new Error('download')
        if (job.data.status === 'done') {
          selection = undefined
          return
        }
        await new Promise<void>((resolve) => {
          wake = resolve
          timer = setTimeout(resolve, 1000)
        })
        if (current !== generation || disposed)
          return
      }
      throw new Error('timeout')
    })
  }
  async function remove(id: string) {
    await run(async () => {
      const result = await api.DELETE('/api/images/senses/{sense_id}/{image_id}', {
        params: {
          path: {
            sense_id: target(),
            image_id: id,
          },
        },
        signal: controller?.signal,
      })
      if (!result.response.ok)
        throw new Error('remove')
    })
  }
  async function retry() {
    if (pendingFile)
      await upload()
    else if (selection)
      await select()
    else if (pendingQuery)
      await search(pendingQuery)
    else
      await refresh()
  }
  watch(target, () => {
    clear()
    void refresh()
  }, { immediate: true })
  onScopeDispose(() => {
    disposed = true
    clear()
  })
  return {
    items,
    results,
    busy,
    error,
    refresh,
    upload,
    search,
    select,
    remove,
    retry,
  }
}
