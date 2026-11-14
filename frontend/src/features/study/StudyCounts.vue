<script setup lang="ts">
import type { components } from '@/api/schema'
import { useI18n } from 'vue-i18n'

defineProps<{
  due: number
  fresh: number
  today: components['schemas']['CompletedCounts']
  dueToday?: boolean
  availableToday?: boolean
}>()
const { t, n } = useI18n()
</script>

<template>
  <dl class="grid grid-cols-2 gap-4 lg:grid-cols-4">
    <div v-for="(value, key) in { due, new: fresh, introduced: today.new, reviewed: today.reviews }" :key="key">
      <dt class="text-sm text-muted">
        {{ t(`study.counts.${key === 'due' && dueToday ? 'dueToday' : key === 'new' && availableToday ? 'availableNew' : key}`) }}
      </dt>
      <dd class="m-0 text-2xl font-semibold">
        {{ n(value) }}
      </dd>
    </div>
  </dl>
</template>
