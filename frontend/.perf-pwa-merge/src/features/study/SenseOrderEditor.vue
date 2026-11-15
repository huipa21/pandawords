<script setup lang="ts">
import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import { useProjectErrors } from '@/features/projects/useProject'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ saved: [] }>()
const { t } = useI18n()
const errorText = useProjectErrors()
const items = ref<components['schemas']['DictionaryRecordRead'][]>([])
const words = ref<Record<string, string>>({})
const loading = ref(false)
const busy = ref(false)
const loaded = ref(false)
const error = ref('')
const saveError = ref('')
const saved = ref(false)
const dirty = ref(false)
const page = ref(1)
const pageSize = 20
const visible = computed(() => items.value.slice((page.value - 1) * pageSize, page.value * pageSize))
let generation = 0
onScopeDispose(() => generation++)

function label(sense: components['schemas']['DictionaryRecordRead']) {
  return typeof sense.fields.definition === 'string'
    ? sense.fields.definition
    : sense.id
}

async function load() {
  const current = ++generation
  loading.value = true
  loaded.value = false
  error.value = ''
  saveError.value = ''
  saved.value = false
  dirty.value = false
  items.value = []
  words.value = {}
  page.value = 1
  try {
    const senses = new Map<string, components['schemas']['DictionaryRecordRead']>()
    const labels: Record<string, string> = {}
    for (let next = 1; ; next++) {
      const result = await api.GET('/api/projects/{project_id}/tree', {
        params: {
          path: { project_id: props.projectId },
          query: { page: next, page_size: 100, include_hidden: false },
        },
      })
      if (current !== generation)
        return
      if (!result.data) {
        error.value = errorText(result.error, result.response.status)
        return
      }
      for (const lemma of result.data.items) {
        if (lemma.effective_hidden)
          continue
        for (const lexeme of lemma.lexemes) {
          if (lexeme.effective_hidden)
            continue
          for (const sense of lexeme.senses) {
            if (!sense.effective_hidden) {
              senses.set(sense.sense.id, sense.sense)
              labels[sense.sense.id] = typeof lemma.lemma.fields.text === 'string'
                ? lemma.lemma.fields.text
                : ''
            }
          }
        }
      }
      if (next * result.data.page_size >= result.data.total)
        break
      if (!result.data.items.length || result.data.page_size <= 0)
        throw new Error('Incomplete tree page')
    }
    items.value = [
      ...senses.values(),
    ]
    words.value = labels
    loaded.value = true
  }
  catch {
    if (current === generation)
      error.value = t('errors.transport')
  }
  finally {
    if (current === generation)
      loading.value = false
  }
}

function move(index: number, delta: number) {
  if (busy.value || index + delta < 0 || index + delta >= items.value.length)
    return
  const [item] = items.value.splice(index, 1)
  items.value.splice(index + delta, 0, item!)
  dirty.value = true
  saved.value = false
  page.value = Math.floor((index + delta) / pageSize) + 1
}

async function save() {
  if (busy.value || !dirty.value || !loaded.value)
    return
  const current = generation
  busy.value = true
  saved.value = false
  saveError.value = ''
  try {
    const result = await api.PUT('/api/projects/{id}/study-plan/order', {
      params: {
        path: { id: props.projectId },
      },
      body: {
        sense_ids: items.value.map(item => item.id),
      },
    })
    if (current !== generation)
      return
    if (result.data) {
      const byId = new Map(items.value.map(item => [item.id, item]))
      items.value = result.data.sense_ids.flatMap(id => byId.has(id)
        ? [
            byId.get(id)!,
          ]
        : [])
      dirty.value = false
      saved.value = true
      emit('saved')
    }
    else {
      saveError.value = errorText(result.error, result.response.status)
    }
  }
  catch {
    if (current === generation)
      saveError.value = t('errors.transport')
  }
  finally {
    if (current === generation)
      busy.value = false
  }
}
</script>

<template>
  <NCard :title="t('study.orderTitle')">
    <div class="grid gap-4">
      <p class="text-muted">
        {{ t('study.orderNotice') }}
      </p>
      <NButton v-if="!loaded && !loading && !error" size="large" @click="load">
        {{ t('study.loadOrder') }}
      </NButton>
      <div v-if="loading" role="status" :aria-label="t('common.loading')">
        <NSkeleton text :repeat="4" />
      </div>
      <ErrorState v-else-if="error" :error="error" @retry="load" />
      <template v-else-if="loaded">
        <EmptyState v-if="!items.length" title-key="study.noSenses" />
        <ol v-else class="m-0 list-none p-0" :aria-label="t('study.orderTitle')">
          <li v-for="(sense, index) in visible" :key="sense.id" class="flex flex-wrap items-center justify-between gap-3 border-b border-divider py-3">
            <span class="min-w-0 flex-1 break-words">
              {{ (page - 1) * pageSize + index + 1 }}.
              <strong class="mr-2">{{ words[sense.id] }}</strong>{{ label(sense) }}
            </span>
            <div class="flex gap-2">
              <NButton size="large" :disabled="busy || (page - 1) * pageSize + index === 0" :aria-label="t('study.moveUp', { name: label(sense) })" @click="move((page - 1) * pageSize + index, -1)">
                {{ t('study.up') }}
              </NButton>
              <NButton size="large" :disabled="busy || (page - 1) * pageSize + index === items.length - 1" :aria-label="t('study.moveDown', { name: label(sense) })" @click="move((page - 1) * pageSize + index, 1)">
                {{ t('study.down') }}
              </NButton>
            </div>
          </li>
        </ol>
        <NPagination v-if="items.length > pageSize" v-model:page="page" :page-size="pageSize" :item-count="items.length" :disabled="busy" />
        <NAlert v-if="saveError" type="error" role="alert">
          {{ saveError }}
        </NAlert>
        <p v-if="saved" role="status">
          {{ t('study.saved') }}
        </p>
        <div v-if="items.length" class="flex flex-wrap gap-3">
          <NButton size="large" type="primary" :disabled="busy || !dirty" :loading="busy" @click="save">
            {{ t('study.saveOrder') }}
          </NButton>
          <NButton size="large" :disabled="busy" @click="load">
            {{ t('study.resetOrder') }}
          </NButton>
        </div>
      </template>
    </div>
  </NCard>
</template>
