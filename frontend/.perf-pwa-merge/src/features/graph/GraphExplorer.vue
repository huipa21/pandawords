<script setup lang="ts">
import type { GraphElements, NodeType, PresentationNode, RelationType } from '@/components/graph/types'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import GraphCanvas from '@/components/graph/GraphCanvas.vue'
import GraphLegend from '@/components/graph/GraphLegend.vue'
import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import { presentGraph, presentNode } from '@/components/graph/types'
import SenseRelations from './SenseRelations.vue'

const props = defineProps<{ projectId?: string, initialFocus?: string }>()
const emit = defineEmits<{ focus: [id: string] }>()
const { t } = useI18n()
const router = useRouter()
const focus = ref(props.initialFocus ?? '')
const selected = ref<PresentationNode>()
const search = ref('')
const seeds = ref<PresentationNode[]>([])
const seedPage = ref(1)
const seedHasMore = ref(false)
const seedLoading = ref(false)
const seedError = ref('')
const depth = ref(1)
const layout = ref<'fcose' | 'dagre'>('fcose')
const direction = ref<'both' | 'incoming' | 'outgoing'>('both')
const nodes = ref<NodeType[]>([])
const relations = ref<RelationType[]>([])
const elements = ref<GraphElements>({ nodes: [], edges: [] })
const loading = ref(false)
const error = ref('')
const canvas = ref<InstanceType<typeof GraphCanvas>>()
let request = 0
let seedRequest = 0

async function loadSeeds(page = 1) {
  const current = ++seedRequest
  seedLoading.value = true
  seedError.value = ''
  try {
    const result = await api.GET('/api/graph/seeds', {
      params: {
        query: {
          q: search.value,
          page,
          page_size: 20,
          ...(props.projectId
            ? { project_id: props.projectId }
            : {}),
        },
      },
    })
    if (current !== seedRequest)
      return
    if (!result.data) {
      seedError.value = result.response.status === 413
        ? 'graph.tooLarge'
        : 'graph.error'
      return
    }
    seeds.value = result.data.map(presentNode)
    seedHasMore.value = result.data.length === 20
    seedPage.value = page
  }
  catch {
    if (current === seedRequest)
      seedError.value = 'graph.error'
  }
  finally {
    if (current === seedRequest)
      seedLoading.value = false
  }
}

async function load(preserveSelection = false) {
  const current = ++request
  const selectedId = preserveSelection ? selected.value?.id : undefined
  error.value = ''
  if (!preserveSelection) {
    elements.value = { nodes: [], edges: [] }
    selected.value = undefined
  }
  if (!focus.value)
    return
  loading.value = true
  try {
    const result = await api.GET('/api/graph', {
      params: {
        query: {
          focus_id: focus.value,
          depth: depth.value,
          direction: direction.value,
          node_types: nodes.value,
          relation_types: relations.value,
        },
      },
    })
    if (current !== request)
      return
    if (result.data) {
      elements.value = presentGraph(result.data)
      selected.value = elements.value.nodes.find(node => node.id === (selectedId ?? focus.value))
    }
    else {
      error.value = result.response.status === 413
        ? 'graph.tooLarge'
        : 'graph.error'
    }
  }
  catch {
    if (current === request)
      error.value = 'graph.error'
  }
  finally {
    if (current === request)
      loading.value = false
  }
}
function setFocus(id: string) {
  focus.value = id
  emit('focus', id)
}
function select(id: string) {
  selected.value = elements.value.nodes.find(node => node.id === id)
}
function expand(id: string) {
  if (focus.value !== id)
    setFocus(id)
  else if (depth.value < 3)
    depth.value++
}
watch([
  focus,
  depth,
  direction,
  nodes,
  relations,
], () => load(), { immediate: true })
watch(() => props.projectId, () => {
  focus.value = props.initialFocus ?? ''
  void loadSeeds()
}, { immediate: true })
onScopeDispose(() => {
  request++
  seedRequest++
})
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="graph-explorer" :aria-label="t('graph.title')">
    <GraphToolbar v-model:layout="layout" v-model:depth="depth" v-model:search="search" v-model:direction="direction" @fit="canvas?.fit()" @search="loadSeeds(1)" />
    <GraphLegend v-model:nodes="nodes" v-model:relations="relations" />
    <section :aria-label="t('graph.focus')" class="space-y-3">
      <p class="text-muted">
        {{ t('graph.bounded') }}
      </p>
      <p v-if="seedLoading" role="status">
        {{ t('common.loading') }}
      </p>
      <div v-else-if="seedError" role="alert">
        <p>{{ t(seedError) }}</p>
        <NButton size="large" @click="loadSeeds(seedPage)">
          {{ t('common.retry') }}
        </NButton>
      </div>
      <template v-else>
        <p v-if="!seeds.length" role="status">
          {{ t('graph.empty') }}
        </p>
        <div class="flex flex-wrap gap-2">
          <NButton v-for="seed in seeds" :key="seed.id" size="large" :aria-pressed="focus === seed.id" @click="setFocus(seed.id)">
            {{ seed.label }}
          </NButton>
        </div>
        <div class="flex gap-2">
          <NButton size="large" :disabled="seedPage <= 1" @click="loadSeeds(seedPage - 1)">
            {{ t('graph.previous') }}
          </NButton>
          <NButton size="large" :disabled="!seedHasMore" @click="loadSeeds(seedPage + 1)">
            {{ t('graph.next') }}
          </NButton>
        </div>
        <SenseRelations v-if="selected?.type === 'sense'" :key="selected.id" :sense-id="selected.id" @changed="load(true)" />
      </template>
    </section>
    <p v-if="loading" role="status">
      {{ t('common.loading') }}
    </p>
    <div v-else-if="error" role="alert" data-testid="graph-error">
      <p>{{ t(error) }}</p>
      <NButton size="large" @click="load()">
        {{ t('common.retry') }}
      </NButton>
    </div>
    <template v-if="focus && !error">
      <p v-if="!elements.nodes.length" role="status">
        {{ t('graph.emptyGraph') }}
      </p>
      <GraphCanvas v-else ref="canvas" :elements="elements" :layout="layout" :focus-id="selected?.id ?? focus" @select="select" @expand="expand" />
      <div v-if="selected" class="flex flex-wrap items-center gap-3" data-testid="graph-selection" role="status">
        <span class="break-words">{{ selected.label }}</span>
        <NButton size="large" :disabled="selected.id === focus && depth >= 3" @click="expand(selected.id)">
          {{ t('graph.expand') }}
        </NButton>
        <NButton v-if="selected.type === 'lemma' || selected.type === 'phrase'" size="large" @click="router.push({ name: 'word', params: { lemmaId: selected.id } })">
          {{ t('graph.open') }}
        </NButton>
      </div>
    </template>
    <p v-else-if="!focus" role="status">
      {{ t('graph.choose') }}
    </p>
  </section>
</template>
