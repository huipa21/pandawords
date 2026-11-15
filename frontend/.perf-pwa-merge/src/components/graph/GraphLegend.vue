<script setup lang="ts">
import type { NodeType, RelationType } from './types'
import { useI18n } from 'vue-i18n'
import { graphEdges, graphNodes } from '@/design/tokens'
import { nodeTypes, relationTypes } from './types'

const props = defineProps<{ nodes: NodeType[], relations: RelationType[] }>()
const emit = defineEmits<{ 'update:nodes': [value: NodeType[]], 'update:relations': [value: RelationType[]] }>()
const { t } = useI18n()
function toggle<T>(items: T[], value: T): T[] {
  return items.includes(value)
    ? items.filter(item => item !== value)
    : [...items, value]
}
function edgeVariable(relation: RelationType) {
  return `var(--pw-edge-${relation in graphEdges
    ? relation
    : 'default'})`
}
</script>

<template>
  <details data-testid="graph-legend">
    <summary class="min-h-12 cursor-pointer py-3 focus-visible:outline">
      {{ t('graph.legend') }}
    </summary>
    <p class="text-muted">
      {{ t('graph.filtersHint') }}
    </p>
    <div class="flex flex-wrap gap-2" role="group" :aria-label="t('graph.nodeFilters')">
      <NButton v-for="node in nodeTypes" :key="node" size="large" :aria-pressed="props.nodes.includes(node)" @click="emit('update:nodes', toggle(props.nodes, node))">
        <span class="mr-2 inline-block h-3 w-3 rounded-sm" :style="{ backgroundColor: `var(--pw-node-${node})` }" aria-hidden="true" />
        {{ t(`graph.nodes.${node}`) }} · {{ t(`graph.shapes.${graphNodes[node].shape}`) }}
      </NButton>
    </div>
    <div class="mt-3 flex flex-wrap gap-2" role="group" :aria-label="t('graph.relationFilters')">
      <NButton v-for="relation in relationTypes" :key="relation" size="large" :aria-pressed="props.relations.includes(relation)" @click="emit('update:relations', toggle(props.relations, relation))">
        <span class="mr-2 inline-block h-1 w-4" :style="{ backgroundColor: edgeVariable(relation) }" aria-hidden="true" />
        {{ t(`graph.relations.${relation}`) }} →
      </NButton>
    </div>
  </details>
</template>
