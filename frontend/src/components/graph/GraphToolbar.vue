<script setup lang="ts">
import type { GraphLayout } from './types'
import { useI18n } from 'vue-i18n'
import { graphMetrics } from '@/design/tokens'

defineProps<{ layout: GraphLayout, depth: number, search: string, direction: 'both' | 'incoming' | 'outgoing' }>()
const emit = defineEmits<{
  'update:layout': [value: GraphLayout]
  'update:depth': [value: number]
  'update:search': [value: string]
  'update:direction': [value: 'both' | 'incoming' | 'outgoing']
  'fit': []
  'search': []
}>()
const { t } = useI18n()
</script>

<template>
  <div class="flex flex-wrap items-end gap-3" role="group" :aria-label="t('graph.toolbar')">
    <label class="min-w-0 flex-1 space-y-2">
      <span>{{ t('graph.search') }}</span>
      <NInput :value="search" size="large" :input-props="{ 'aria-label': t('graph.search') }" @update:value="emit('update:search', $event)" @keyup.enter="emit('search')" />
    </label>
    <NButton size="large" @click="emit('search')">
      {{ t('graph.search') }}
    </NButton>
    <label class="space-y-2">
      <span>{{ t('graph.layout') }}</span>
      <NSelect :style="{ width: graphMetrics.controlWidth }" size="large" :aria-label="t('graph.layout')" :value="layout" :options="['fcose', 'dagre'].map(value => ({ value, label: t(`graph.layouts.${value}`) }))" @update:value="emit('update:layout', $event)" />
    </label>
    <label class="space-y-2">
      <span>{{ t('graph.depth') }}</span>
      <NSelect :style="{ width: graphMetrics.controlWidth }" size="large" :aria-label="t('graph.depth')" :value="depth" :options="[0, 1, 2, 3].map(value => ({ value, label: String(value) }))" @update:value="emit('update:depth', $event)" />
    </label>
    <label class="space-y-2">
      <span>{{ t('graph.direction') }}</span>
      <NSelect :style="{ width: graphMetrics.controlWidth }" size="large" :aria-label="t('graph.direction')" :value="direction" :options="['both', 'incoming', 'outgoing'].map(value => ({ value, label: t(`graph.directions.${value}`) }))" @update:value="emit('update:direction', $event)" />
    </label>
    <NButton size="large" @click="emit('fit')">
      {{ t('graph.fit') }}
    </NButton>
  </div>
</template>
