import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { candidateView } from './dictionaryAdapters'
import { useProjectErrors } from './useProject'

export function useAddWord(projectId: () => string, show: () => boolean) {
  const { t } = useI18n()
  const errorText = useProjectErrors()
  const text = ref('')
  const candidates = ref<components['schemas']['Candidate'][]>([])
  const candidateIndex = ref(0)
  const selected = ref<string[]>()
  const searching = ref(false)
  const submitting = ref(false)
  const searched = ref(false)
  const error = ref('')
  const added = ref(false)
  const jobs = ref<components['schemas']['JobRead'][]>([])
  const candidate = computed(() => candidates.value[candidateIndex.value])
  const view = computed(() => candidate.value
    ? candidateView(candidate.value)
    : undefined)
  const selectedSenses = computed(() => candidate.value?.lexemes.flatMap(lexeme =>
    lexeme.senses.filter(sense => selected.value?.includes(JSON.stringify(sense.id))).map(sense => sense.id),
  ) ?? [])
  const busy = computed(() => searching.value || submitting.value)
  let controller: AbortController | undefined
  let request = 0

  function invalidate() {
    request++
    controller?.abort()
    searching.value = false
    submitting.value = false
  }
  function choose(index: number) {
    candidateIndex.value = index
    selected.value = candidate.value?.lexemes.flatMap(lexeme =>
      lexeme.senses.filter(sense => sense.common).map(sense => JSON.stringify(sense.id)),
    ) ?? []
    added.value = false
    error.value = ''
  }
  async function search() {
    if (!text.value.trim() || busy.value || !show())
      return
    invalidate()
    const current = request
    controller = new AbortController()
    searching.value = true
    candidates.value = []
    selected.value = []
    searched.value = false
    error.value = ''
    added.value = false
    try {
      const result = await api.POST('/api/dictionary/candidates', {
        body: {
          text: text.value.trim(),
        },
        signal: controller.signal,
      })
      if (current !== request)
        return
      if (result.data) {
        candidates.value = result.data.candidates
        searched.value = true
        choose(0)
      }
      else {
        error.value = errorText(result.error, result.response.status)
      }
    }
    catch {
      if (current === request)
        error.value = t('errors.transport')
    }
    finally {
      if (current === request)
        searching.value = false
    }
  }
  async function submit() {
    if (!candidate.value || !selectedSenses.value.length || busy.value || !show())
      return
    const current = ++request
    controller = new AbortController()
    submitting.value = true
    error.value = ''
    added.value = false
    try {
      const result = await api.POST('/api/projects/{id}/dictionary', {
        params: {
          path: {
            id: projectId(),
          },
        },
        body: { lemma_key: candidate.value.lemma.id, selected_senses: selectedSenses.value },
        signal: controller.signal,
      })
      if (current !== request)
        return
      if (result.data) {
        const merged = new Map(jobs.value.map(job => [job.id, job]))
        for (const job of result.data.jobs) {
          const previous = merged.get(job.id)
          if (!previous || !['done', 'failed'].includes(previous.status))
            merged.set(job.id, job)
        }
        jobs.value = [
          ...merged.values(),
        ]
        added.value = true
        return result.data
      }
      error.value = errorText(result.error, result.response.status)
    }
    catch {
      if (current === request)
        error.value = t('errors.transport')
    }
    finally {
      if (current === request)
        submitting.value = false
    }
  }
  watch(text, () => {
    invalidate()
    candidates.value = []
    selected.value = []
    searched.value = false
    added.value = false
    error.value = ''
  }, { flush: 'sync' })
  watch(show, (visible) => {
    if (!visible)
      invalidate()
  }, { flush: 'sync' })
  watch(projectId, () => {
    invalidate()
    text.value = ''
    candidates.value = []
    selected.value = []
    searched.value = false
    error.value = ''
    added.value = false
    jobs.value = []
  }, { flush: 'sync' })
  onScopeDispose(invalidate)
  return {
    text,
    candidates,
    candidateIndex,
    selected,
    view,
    selectedSenses,
    searching,
    submitting,
    searched,
    busy,
    error,
    added,
    jobs,
    choose,
    search,
    submit,
  }
}
