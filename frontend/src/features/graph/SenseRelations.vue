<script setup lang="ts">
import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import ConfirmAction from '@/components/app/ConfirmAction.vue'

type Relation = components['schemas']['RelationRead']
type Kind = components['schemas']['RelationCreate']['type']
type Node = components['schemas']['SenseNode']
const props = defineProps<{ senseId: string }>()
const emit = defineEmits<{ changed: [] }>()
const { t } = useI18n()
const kinds: Kind[] = [
  'synonym',
  'antonym',
  'hypernym',
  'hyponym',
  'confusable',
  'collocation',
  'default',
]
const options = computed(() => kinds.map(value => ({
  value,
  label: t(`relations.types.${value}`),
})))
const kind = ref<Kind>('synonym')
const query = ref('')
const candidates = ref<Node[]>([])
const target = ref<Node>()
const items = ref<Relation[]>([])
const removing = ref<Relation>()
const page = ref(1)
const searchPage = ref(1)
const hasMore = ref(false)
const searchMore = ref(false)
const loading = ref(false)
const searching = ref(false)
const busy = ref(false)
const error = ref('')
const searchError = ref(false)
const feedback = ref('')
let disposed = false
let searchRequest = 0
onScopeDispose(() => {
  disposed = true
  searchRequest++
})

async function load(next = page.value) {
  loading.value = true
  error.value = ''
  try {
    const result = await api.GET('/api/relations', {
      params: {
        query: { sense_id: props.senseId, page: next, page_size: 20 },
      },
    })
    if (disposed)
      return
    if (!result.data)
      throw new Error('load')
    items.value = result.data
    page.value = next
    hasMore.value = result.data.length === 20
  }
  catch {
    if (!disposed)
      error.value = 'relations.failed'
  }
  finally {
    if (!disposed)
      loading.value = false
  }
}
async function search(next = 1) {
  const request = ++searchRequest
  searching.value = true
  searchError.value = false
  try {
    const result = await api.GET('/api/graph/seeds', {
      params: {
        query: {
          q: query.value,
          node_types: ['sense'],
          page: next,
          page_size: 20,
        },
      },
    })
    if (disposed || request !== searchRequest)
      return
    if (!result.data)
      throw new Error('search')
    candidates.value = result.data.filter((node): node is Node => node.table === 'sense' && node.id !== props.senseId)
    searchPage.value = next
    searchMore.value = result.data.length === 20
  }
  catch {
    if (!disposed && request === searchRequest)
      searchError.value = true
  }
  finally {
    if (!disposed && request === searchRequest)
      searching.value = false
  }
}
async function create() {
  if (busy.value)
    return
  if (!target.value || target.value.id === props.senseId) {
    error.value = 'relations.choose'
    return
  }
  busy.value = true
  error.value = ''
  feedback.value = ''
  try {
    const result = await api.POST('/api/relations', {
      body: { start: props.senseId, end: target.value.id, type: kind.value },
    })
    if (disposed)
      return
    if (!result.data) {
      error.value = result.response.status === 422
        ? 'relations.invalid'
        : 'relations.failed'
      return
    }
    feedback.value = result.data.created ? 'relations.created' : 'relations.duplicate'
    emit('changed')
    await load(1)
  }
  catch {
    if (!disposed)
      error.value = 'relations.failed'
  }
  finally {
    if (!disposed)
      busy.value = false
  }
}
async function remove() {
  if (busy.value || !removing.value)
    return
  busy.value = true
  error.value = ''
  feedback.value = ''
  try {
    const result = await api.DELETE('/api/relations/{id}', {
      params: {
        path: { id: removing.value.id },
      },
    })
    if (disposed)
      return
    if (!result.response.ok)
      throw new Error('remove')
    removing.value = undefined
    feedback.value = 'relations.removed'
    emit('changed')
    await load(1)
  }
  catch {
    if (!disposed)
      error.value = 'relations.failed'
  }
  finally {
    if (!disposed)
      busy.value = false
  }
}
void load(1)
</script>

<template>
  <section class="space-y-3" data-testid="sense-relations" :aria-label="t('relations.title')">
    <h3 class="font-semibold">
      {{ t('relations.title') }}
    </h3>
    <p class="text-muted">
      {{ t('relations.policy') }}
    </p>
    <p v-if="feedback" role="status">
      {{ t(feedback) }}
    </p>
    <div v-if="error" role="alert">
      <p>{{ t(error) }}</p>
      <NButton size="large" :disabled="busy || loading" @click="load()">
        {{ t('common.retry') }}
      </NButton>
    </div>
    <p v-if="loading" role="status">
      {{ t('common.loading') }}
    </p>
    <p v-else-if="!items.length" class="text-muted">
      {{ t('relations.empty') }}
    </p>
    <div v-for="item in items" :key="item.id" class="flex flex-wrap items-center gap-3">
      <span class="break-words">{{ item.start_label }} → {{ t(`relations.types.${item.type}`) }} → {{ item.end_label }}</span>
      <span v-if="item.readonly" class="text-muted">{{ t('relations.source') }}</span>
      <NButton v-else size="large" :disabled="busy || loading" data-testid="relation-remove" @click="removing = item">
        {{ t('relations.remove') }}
      </NButton>
    </div>
    <div class="flex gap-2">
      <NButton size="large" :disabled="page <= 1 || loading || busy" @click="load(page - 1)">
        {{ t('graph.previous') }}
      </NButton>
      <NButton size="large" :disabled="!hasMore || loading || busy" @click="load(page + 1)">
        {{ t('graph.next') }}
      </NButton>
    </div>
    <NFormItem :label="t('relations.search')" :label-props="{ for: `relation-search-${senseId}` }">
      <NInput v-model:value="query" :disabled="busy" :input-props="{ id: `relation-search-${senseId}` }" @keydown.enter.prevent="search()" />
    </NFormItem>
    <NButton size="large" :loading="searching" :disabled="busy" data-testid="relation-search" @click="search()">
      {{ t('relations.search') }}
    </NButton>
    <div v-if="searchError" role="alert">
      <p>{{ t('relations.failed') }}</p>
      <NButton size="large" @click="search(searchPage)">
        {{ t('common.retry') }}
      </NButton>
    </div>
    <p v-if="!searching && !candidates.length" class="text-muted">
      {{ t('relations.noCandidates') }}
    </p>
    <div class="flex flex-wrap gap-2">
      <NButton v-for="candidate in candidates" :key="candidate.id" size="large" :disabled="busy" :aria-pressed="target?.id === candidate.id" data-testid="relation-target" @click="target = candidate">
        {{ candidate.fields.definition }}
      </NButton>
    </div>
    <div class="flex gap-2">
      <NButton size="large" :disabled="searchPage <= 1 || searching || busy" @click="search(searchPage - 1)">
        {{ t('graph.previous') }}
      </NButton>
      <NButton size="large" :disabled="!searchMore || searching || busy" @click="search(searchPage + 1)">
        {{ t('graph.next') }}
      </NButton>
    </div>
    <p v-if="target" role="status" class="break-words">
      {{ t('relations.selected', { label: target.fields.definition }) }}
    </p>
    <NFormItem :label="t('relations.type')" :label-props="{ for: `relation-type-${senseId}` }">
      <NSelect v-model:value="kind" :options="options" :disabled="busy" :input-props="{ id: `relation-type-${senseId}` }" />
    </NFormItem>
    <NButton size="large" :disabled="busy || loading" :loading="busy" data-testid="relation-create" @click="create">
      {{ t('relations.create') }}
    </NButton>
    <ConfirmAction :show="!!removing" title-key="relations.remove" :content-key="error ? 'relations.failed' : 'relations.confirmRemove'" :loading="busy" @confirm="remove" @cancel="removing = undefined" />
  </section>
</template>
