<script setup lang="ts">
import type { ExercisePrompt } from './types'
import { NButton } from 'naive-ui'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { acceptsShortcut, isEditing } from './keyboard'

const props = withDefaults(defineProps<{
  choices: ExercisePrompt['choices']
  modelValue?: string
  disabled?: boolean
}>(), { modelValue: '', disabled: false })
const emit = defineEmits<{
  'update:modelValue': [answer: string]
  'submit': []
}>()
const { t } = useI18n()
const root = ref<HTMLElement>()

function keydown(event: KeyboardEvent) {
  if (!acceptsShortcut(event) || isEditing(event))
    return
  const index = ['1', '2', '3', '4'].indexOf(event.key)
  if (index < 0 && event.key !== 'Enter')
    return
  event.stopPropagation()
  event.preventDefault()
  if (props.disabled)
    return
  const choice = props.choices[index]
  if (index >= 0 && choice)
    emit('update:modelValue', choice.id)
  else if (event.key === 'Enter' && props.choices.some(item => item.id === props.modelValue))
    emit('submit')
}

defineExpose({
  focus: () => root.value?.querySelector('button')?.focus(),
})
</script>

<template>
  <div
    ref="root" role="group" :aria-label="t('exercise.choices')"
    class="grid grid-cols-1 gap-3 sm:grid-cols-2" @keydown="keydown"
  >
    <NButton
      v-for="(choice, index) in choices" :key="choice.id"
      size="large" class="choice-option h-auto whitespace-normal py-3"
      :disabled="disabled" :type="modelValue === choice.id ? 'primary' : 'default'"
      :aria-pressed="modelValue === choice.id" :aria-keyshortcuts="String(index + 1)"
      @click="emit('update:modelValue', choice.id)"
    >
      <span class="break-words">{{ index + 1 }}. {{ choice.label }}</span>
    </NButton>
  </div>
</template>

<style scoped>
.choice-option { min-height: var(--pw-layout-touch-target); }
</style>
