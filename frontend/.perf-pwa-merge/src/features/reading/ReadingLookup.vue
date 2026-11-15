<script setup lang="ts">
import type { Occurrence } from './readingText'
import type { components } from '@/api/schema'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'

const props = defineProps<{ occurrence: Occurrence, sentenceId: string, projectId: string | null }>()
const emit = defineEmits<{ linked: [], dismiss: [] }>()
const { t } = useI18n()
const query = ref('')
const candidates = ref<components['schemas']['Candidate'][]>([])
const selected = ref<string | null>(null)
const busy = ref(false)
const failed = ref(false)
const searched = ref(false)
const addedSense = ref<string>()
let version = 0
const options = computed(() => candidates.value.flatMap(candidate => candidate.lexemes.flatMap(lexeme =>
  lexeme.senses.map(sense => ({
    label: `${candidate.lemma.text} · ${lexeme.lexeme.pos} · ${sense.definition}`,
    value: JSON.stringify(sense.id),
    candidate,
    sense,
  })),
)))
watch(() => [props.sentenceId, ...props.occurrence.span], () => {
  version++
  query.value = props.occurrence.text
  candidates.value = []
  selected.value = null
  addedSense.value = undefined
  searched.value = false
  busy.value = false
  failed.value = false
}, { immediate: true })
watch(() => props.projectId, () => {
  version++
  addedSense.value = undefined
  busy.value = false
})
async function lookup() {
  const current = ++version
  busy.value = true
  failed.value = false
  try {
    const result = await api.POST('/api/dictionary/candidates', {
      body: {
        text: query.value.trim(),
      },
    })
    if (current !== version)
      return
    if (!result.data)
      throw new Error('unavailable')
    candidates.value = result.data.candidates
    selected.value = null
    addedSense.value = undefined
    searched.value = true
  }
  catch {
    if (current === version)
      failed.value = true
  }
  finally {
    if (current === version)
      busy.value = false
  }
}
async function add() {
  const choice = options.value.find(item => item.value === selected.value)
  if (!props.projectId || !choice || busy.value)
    return
  const current = ++version
  busy.value = true
  failed.value = false
  try {
    if (!addedSense.value) {
      const result = await api.POST('/api/projects/{id}/dictionary', {
        params: {
          path: { id: props.projectId },
        },
        body: {
          lemma_key: choice.candidate.lemma.id,
          selected_senses: [choice.sense.id],
        },
      })
      if (current !== version)
        return
      if (!result.data?.selected_sense_ids?.[0])
        throw new Error('unavailable')
      addedSense.value = result.data.selected_sense_ids[0]
    }
    const result = await api.PUT('/api/content/sentence/{id}/occurrences', {
      params: {
        path: { id: props.sentenceId },
      },
      body: { span: props.occurrence.span, sense_id: addedSense.value },
    })
    if (current !== version)
      return
    if (!result.data)
      throw new Error('unavailable')
    emit('linked')
  }
  catch {
    if (current === version)
      failed.value = true
  }
  finally {
    if (current === version)
      busy.value = false
  }
}
</script>

<template>
  <section class="grid gap-4" :aria-label="t('reading.lookup')">
    <p>{{ t('reading.explicit') }}</p>
    <label>
      {{ t('reading.query') }}
      <NInput v-model:value="query" :disabled="busy" :input-props="{ 'aria-label': t('reading.query') }" @keyup.enter="lookup" />
    </label>
    <NButton size="large" :loading="busy" :disabled="busy || !query.trim()" @click="lookup">
      {{ t('reading.lookup') }}
    </NButton>
    <label v-if="options.length">
      {{ t('reading.sense') }}
      <NSelect v-model:value="selected" :options="options" :disabled="busy || !!addedSense" :aria-label="t('reading.sense')" />
    </label>
    <p v-else-if="searched" role="status">
      {{ t('reading.noCandidates') }}
    </p>
    <p v-if="!projectId">
      {{ t('reading.chooseProject') }}
    </p>
    <p v-if="failed" role="alert">
      {{ t('reading.addFailed') }}
    </p>
    <div class="flex flex-wrap gap-2">
      <NButton size="large" type="primary" :loading="busy" :disabled="busy || !projectId || !selected" @click="add">
        {{ t(failed ? 'reading.retryAdd' : 'reading.add') }}
      </NButton>
      <NButton size="large" @click="emit('dismiss')">
        {{ t('reading.dismiss') }}
      </NButton>
    </div>
  </section>
</template>
