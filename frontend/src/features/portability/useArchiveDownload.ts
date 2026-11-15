import type { TransferError } from './archive'
import { onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { downloadName, isAbort, saveBlob, skippedMedia, useTransferErrors } from './archive'

export interface DownloadResult {
  data?: unknown
  error?: unknown
  response: Response
}

/** Authenticated archive download with cancel; the blob is saved locally, no URL is shown. */
export function useArchiveDownload(fallbackName: string) {
  const { t } = useI18n()
  const errorText = useTransferErrors()
  const busy = ref(false)
  const error = ref<TransferError>()
  const skipped = ref(0)
  const savedName = ref('')
  let controller: AbortController | undefined

  async function download(request: (signal: AbortSignal) => Promise<DownloadResult>) {
    if (busy.value)
      return false
    controller = new AbortController()
    const current = controller
    busy.value = true
    error.value = undefined
    skipped.value = 0
    savedName.value = ''
    try {
      const result = await request(current.signal)
      if (current.signal.aborted)
        return false
      if (!result.response.ok || !(result.data instanceof Blob)) {
        error.value = errorText(result.error, result.response.status)
        return false
      }
      savedName.value = downloadName(result.response, fallbackName)
      skipped.value = skippedMedia(result.response)
      saveBlob(result.data, savedName.value)
      return true
    }
    catch (caught) {
      if (!isAbort(caught) && !current.signal.aborted) {
        error.value = {
          text: t('errors.transport'),
          stage: '',
          problems: [],
        }
      }
      return false
    }
    finally {
      if (controller === current) {
        busy.value = false
        controller = undefined
      }
    }
  }

  function cancel() {
    controller?.abort()
    controller = undefined
    busy.value = false
  }

  onScopeDispose(cancel)
  return {
    busy,
    error,
    skipped,
    savedName,
    download,
    cancel,
  }
}
