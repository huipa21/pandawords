<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  done: number
  remaining: number
  newCount: number
  reviewCount: number
}>()
const { t } = useI18n()
const total = computed(() => props.done + props.remaining)
</script>

<template>
  <section :aria-label="t('exercise.progress')" class="space-y-2">
    <div class="flex flex-wrap justify-between gap-2 text-sm" role="status">
      <span>{{ t('exercise.doneRemaining', { done, remaining }) }}</span>
      <span class="text-muted">{{ t('exercise.newReview', { new: newCount, review: reviewCount }) }}</span>
    </div>
    <progress
      class="h-2 w-full" :value="done" :max="total || 1"
      :aria-label="t('exercise.progress')" :aria-valuetext="t('exercise.doneRemaining', { done, remaining })"
    />
  </section>
</template>

<style scoped>
progress { accent-color: var(--pw-color-primary); }
</style>
