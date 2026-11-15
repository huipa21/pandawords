<script setup lang="ts">
import type { Rating } from './types'
import { NButton } from 'naive-ui'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { acceptsShortcut, isEditing } from './keyboard'

const props = withDefaults(defineProps<{
  autoRating: Rating
  disabled?: boolean
  loading?: boolean
}>(), { disabled: false, loading: false })
const emit = defineEmits<{
  change: [rating: Rating]
  confirm: [rating: Rating]
}>()
const { t } = useI18n()
const selected = ref<Rating>(props.autoRating)
const root = ref<HTMLElement>()
const ratings = [
  { value: 1, name: 'again' },
  { value: 2, name: 'hard' },
  { value: 3, name: 'good' },
  { value: 4, name: 'easy' },
] as const
watch(() => props.autoRating, value => selected.value = value)

function select(rating: Rating) {
  if (props.disabled || props.loading)
    return
  selected.value = rating
  emit('change', rating)
}
function confirm() {
  if (!props.disabled && !props.loading)
    emit('confirm', selected.value)
}
function keydown(event: KeyboardEvent) {
  if (!acceptsShortcut(event) || isEditing(event))
    return
  const rating = ratings.find(item => String(item.value) === event.key)
  if (!rating && event.key !== 'Enter' && event.key !== ' ')
    return
  event.preventDefault()
  event.stopPropagation()
  if (rating)
    select(rating.value)
  else
    confirm()
}
function focus() {
  root.value?.querySelector<HTMLButtonElement>('[aria-pressed="true"]')?.focus()
}
defineExpose({ focus })
</script>

<template>
  <div ref="root" class="space-y-3" @keydown="keydown">
    <p class="m-0 text-sm text-muted">
      {{ t('exercise.autoRating', { rating: t(`exercise.rating.${ratings[autoRating - 1]!.name}`) }) }}
    </p>
    <div role="group" :aria-label="t('exercise.ratingLabel')" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
      <NButton
        v-for="rating in ratings" :key="rating.value" size="large"
        :disabled="disabled || loading" :aria-pressed="selected === rating.value"
        :aria-keyshortcuts="String(rating.value)" :data-rating="rating.name"
        :strong="selected === rating.value" :dashed="selected !== rating.value"
        class="rating-option" @click="select(rating.value)"
      >
        {{ rating.value }}. {{ t(`exercise.rating.${rating.name}`) }}
      </NButton>
    </div>
    <NButton size="large" type="primary" class="rating-confirm w-full" :disabled="disabled || loading" :loading="loading" @click="confirm">
      {{ t('exercise.confirmRating') }}
    </NButton>
    <p class="m-0 text-sm text-muted">
      {{ t('exercise.ratingShortcuts') }}
    </p>
  </div>
</template>

<style scoped>
.rating-option, .rating-confirm { min-height: var(--pw-layout-touch-target); }
.rating-option[data-rating='again'] { color: var(--pw-rating-again); }
.rating-option[data-rating='hard'] { color: var(--pw-rating-hard); }
.rating-option[data-rating='good'] { color: var(--pw-rating-good); }
.rating-option[data-rating='easy'] { color: var(--pw-rating-easy); }
</style>
