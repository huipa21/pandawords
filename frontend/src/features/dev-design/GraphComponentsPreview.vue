<script setup lang="ts">
import type { GraphElements, NodeType, RelationType } from '@/components/graph/types'
import type { ThemeMode } from '@/design/tokens'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import GraphCanvas from '@/components/graph/GraphCanvas.vue'
import GraphLegend from '@/components/graph/GraphLegend.vue'
import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import { graphNodes } from '@/design/tokens'

defineProps<{ mode: ThemeMode }>()
const { t } = useI18n({ useScope: 'global' })
const layout = ref<'fcose' | 'dagre'>('fcose')
const depth = ref(1)
const search = ref('')
const direction = ref<'both' | 'incoming' | 'outgoing'>('both')
const nodes = ref<NodeType[]>([])
const relations = ref<RelationType[]>([])
const selected = ref('sample-0')
const canvas = ref<InstanceType<typeof GraphCanvas>>()
const types = Object.keys(graphNodes) as (keyof typeof graphNodes)[]
function sample(count: number): GraphElements {
  return {
    nodes: Array.from({ length: count }, (_, i) => ({
      id: `sample-${i}`,
      label: `${t(`graph.nodes.${types[i % types.length]}`)} ${i + 1}`,
      type: types[i % types.length]!,
    })),
    edges: Array.from({ length: count - 1 }, (_, i) => ({
      id: `edge-${i}`,
      source: `sample-${Math.floor(i / 2)}`,
      target: `sample-${i + 1}`,
      type: i % 2
        ? 'synonym'
        : 'antonym',
    })),
  }
}
</script>

<template>
  <section class="min-w-0 space-y-4" data-testid="graph-preview">
    <h3 class="text-lg font-semibold">
      {{ t('graph.title') }}
    </h3>
    <GraphToolbar v-model:layout="layout" v-model:depth="depth" v-model:search="search" v-model:direction="direction" @fit="canvas?.fit()" />
    <GraphLegend v-model:nodes="nodes" v-model:relations="relations" />
    <h4>{{ t('graph.sparse') }}</h4>
    <GraphCanvas ref="canvas" :elements="sample(4)" :theme="mode" :layout="layout" :focus-id="selected" @select="selected = $event" @expand="selected = $event" />
    <h4>{{ t('graph.dense') }}</h4>
    <GraphCanvas :elements="sample(64)" :theme="mode" :layout="layout" :focus-id="selected" @select="selected = $event" @expand="selected = $event" />
  </section>
</template>
