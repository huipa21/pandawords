import type { ArchiveProblem, TransferError } from './archive'
import { onScopeDispose, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { checkArchive, isAbort, useTransferErrors } from './archive'

export type ProgressChoice = 'auto' | 'on' | 'off'
export type UploadState = 'idle' | 'uploading' | 'success' | 'error' | 'cancelled'

export interface UploadResult<T> {
  data?: T
  error?: unknown
  response: Response
}

export type UploadRequest<T> = (file: File, includeProgress: boolean | undefined, signal: AbortSignal) => Promise<UploadResult<T>>

/**
 * Upload state for one archive form. A failure or cancellation keeps the selected file and
 * options so the same submission can be retried.
 */
export function useArchiveUpload<T>(request: UploadRequest<T>, initialChoice: ProgressChoice) {
  const { t } = useI18n()
  const errorText = useTransferErrors()
  const file = shallowRef<File>()
  const problem = ref<ArchiveProblem | null>(null)
  const choice = ref<ProgressChoice>(initialChoice)
  const state = ref<UploadState>('idle')
  const summary = shallowRef<T>()
  const error = ref<TransferError>()
  let controller: AbortController | undefined

  function select(next: File | undefined) {
    if (state.value === 'uploading')
      return
    file.value = next
    problem.value = next
      ? checkArchive(next)
      : null
    state.value = 'idle'
    error.value = undefined
    summary.value = undefined
  }

  async function submit() {
    if (!file.value || problem.value || state.value === 'uploading')
      return false
    controller = new AbortController()
    const current = controller
    state.value = 'uploading'
    error.value = undefined
    summary.value = undefined
    const includeProgress = choice.value === 'auto'
      ? undefined
      : choice.value === 'on'
    try {
      const result = await request(file.value, includeProgress, current.signal)
      if (current.signal.aborted)
        return false
      if (result.data && result.response.ok) {
        summary.value = result.data
        state.value = 'success'
        return true
      }
      error.value = errorText(result.error, result.response.status)
      state.value = 'error'
      return false
    }
    catch (caught) {
      if (current.signal.aborted || isAbort(caught))
        return false
      error.value = {
        text: t('errors.transport'),
        stage: '',
        problems: [],
      }
      state.value = 'error'
      return false
    }
    finally {
      if (controller === current)
        controller = undefined
    }
  }

  function cancel() {
    if (state.value !== 'uploading')
      return
    controller?.abort()
    controller = undefined
    state.value = 'cancelled'
  }

  function reset() {
    cancel()
    select(undefined)
    choice.value = initialChoice
  }

  onScopeDispose(() => controller?.abort())
  return {
    file,
    problem,
    choice,
    state,
    summary,
    error,
    select,
    submit,
    cancel,
    reset,
  }
}
