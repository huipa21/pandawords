import { useMessage } from 'naive-ui'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { useWordAudio } from '@/components/word/audio'
import { useWordErrors } from './useLemmaDetail'

export function usePronunciation(id: () => string) {
  const { t } = useI18n()
  const message = useMessage()
  const errorText = useWordErrors()
  const audio = useWordAudio()
  const owner = Symbol('lemma-pronunciation')
  const loading = ref(false)
  const current = ref<string>()
  const playing = computed(() => audio.active.value === owner)
  let url: string | undefined
  let controller: AbortController | undefined
  let generation = 0

  function clear() {
    generation++
    controller?.abort()
    controller = undefined
    audio.stop(owner)
    if (url)
      URL.revokeObjectURL(url)
    url = undefined
    loading.value = false
    current.value = undefined
  }

  async function play(mediaId: string, key = mediaId) {
    if (current.value === key && (loading.value || playing.value)) {
      clear()
      return
    }
    clear()
    if (!mediaId) {
      message.info(t('lemmaDetail.missingAudio'))
      return
    }
    current.value = key
    const request = generation
    controller = new AbortController()
    loading.value = true
    try {
      const result = await api.GET('/api/media/{rid}', {
        params: {
          path: { rid: mediaId },
        },
        parseAs: 'blob',
        signal: controller.signal,
      })
      if (request !== generation)
        return
      if (!result.response.ok) {
        message.error(result.response.status === 404
          ? t('lemmaDetail.missingAudio')
          : errorText(result.error, result.response.status))
        return
      }
      if (!(result.data instanceof Blob) || result.data.size === 0) {
        message.error(t('word.audio.error'))
        return
      }
      url = URL.createObjectURL(result.data)
      await audio.play(owner, url, () => message.error(t('word.audio.error')))
    }
    catch {
      if (request === generation)
        message.error(t('word.audio.error'))
    }
    finally {
      if (request === generation)
        loading.value = false
    }
  }

  watch(id, clear)
  onScopeDispose(clear)
  return { current, loading, playing, play }
}
