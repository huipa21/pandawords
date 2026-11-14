<script setup lang="ts">
import type { components } from '@/api/schema'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import PhraseAddAction from './PhraseAddAction.vue'

const props = defineProps<{ lemmaId: string }>()
const { t } = useI18n()
const router = useRouter()
const items = ref<components['schemas']['ContainingPhraseRead'][]>([])
const loading = ref(false)
const error = ref('')
const offset = ref(0)
const hasMore = ref(false)
let generation = 0
async function load(reset = false) {
  const current = ++generation
  if (reset) {
    items.value = []
    offset.value = 0
    hasMore.value = false
  }
  loading.value = true
  error.value = ''
  try {
    const result = await api.GET('/api/dictionary/{table}/{id}/phrases', {
      params: {
        path: { table: 'lemma', id: props.lemmaId },
        query: { offset: offset.value, limit: 20 },
      },
    })
    if (current !== generation)
      return
    if (!result.data)
      throw new Error()
    items.value.push(...result.data.items)
    offset.value += result.data.limit
    hasMore.value = result.data.has_more
  }
  catch {
    if (current === generation)
      error.value = t('phrases.error')
  }
  finally {
    if (current === generation)
      loading.value = false
  }
}
watch(() => props.lemmaId, () => load(true), { immediate: true })
onScopeDispose(() => generation++)
</script>

<template>
  <NCard :title="t('phrases.title')" data-testid="containing-phrases">
    <div class="space-y-4">
      <p class="text-muted">
        {{ t('phrases.composition') }}
      </p>
      <p v-if="loading" role="status">
        {{ t('common.loading') }}
      </p>
      <div v-if="error" role="alert">
        {{ error }}
        <NButton size="large" @click="load()">
          {{ t('phrases.retry') }}
        </NButton>
      </div>
      <p v-if="!loading && !error && !items.length" role="status">
        {{ t('phrases.empty') }}
      </p>
      <article v-for="item in items" :key="item.entry.lemma.id" class="space-y-3">
        <NButton
          size="large" data-testid="phrase-detail"
          @click="router.push({ name: 'word', params: { lemmaId: item.entry.lemma.id } })"
        >
          {{ item.entry.lemma.fields.text }}
        </NButton>
        <p v-for="sense in item.entry.lexemes.flatMap(lexeme => lexeme.senses)" :key="sense.id">
          {{ sense.fields.definition }}
        </p>
        <PhraseAddAction v-if="item.candidate" :text="item.candidate.lemma.text" />
      </article>
      <NButton v-if="hasMore" size="large" :disabled="loading" @click="load()">
        {{ t('phrases.more') }}
      </NButton>
    </div>
  </NCard>
</template>
