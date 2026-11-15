<script setup lang="ts">
import type { ExerciseFeedback } from './types'
import { NInput } from 'naive-ui'
import { ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import { acceptsShortcut } from './keyboard'

const props = withDefaults(defineProps<{
  modelValue?: string
  disabled?: boolean
  feedback?: ExerciseFeedback
}>(), { modelValue: '', disabled: false })
const emit = defineEmits<{
  'update:modelValue': [answer: string]
  'submit': []
}>()
const { t } = useI18n()
const id = useId()
const input = ref<InstanceType<typeof NInput>>()
function keydown(event: KeyboardEvent) {
  if (event.key !== 'Enter' || !acceptsShortcut(event))
    return
  event.preventDefault()
  event.stopPropagation()
  if (!props.disabled && !props.feedback && props.modelValue.trim())
    emit('submit')
}
defineExpose({
  focus: () => input.value?.focus(),
})
</script>

<template>
  <div class="space-y-2">
    <label :for="id" class="block font-medium">{{ t('exercise.answer') }}</label>
    <NInput
      ref="input" size="large" :value="modelValue"
      :disabled="disabled || Boolean(feedback)" :input-props="{ id, 'autocapitalize': 'off', 'autocomplete': 'off', 'spellcheck': false, 'aria-describedby': feedback && !feedback.correct ? `${id}-feedback` : undefined }"
      :status="feedback && !feedback.correct ? 'error' : undefined"
      @update:value="emit('update:modelValue', $event)" @keydown="keydown"
    />
    <div v-if="feedback && !feedback.correct" :id="`${id}-feedback`" class="space-y-2 break-words">
      <p class="m-0">
        {{ t('exercise.yourAnswer') }} <del class="text-error">{{ modelValue || t('exercise.noAnswer') }}</del>
      </p>
      <p class="m-0">
        {{ t('exercise.expectedAnswer') }} <ins class="text-success">{{ feedback.answer }}</ins>
      </p>
    </div>
  </div>
</template>
