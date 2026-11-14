<script setup lang="ts">
import type { ExerciseAnswer, ExerciseFeedback, ExercisePrompt, Rating } from './types'
import { NButton } from 'naive-ui'
import { computed, nextTick, onMounted, ref, useId, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChoiceGrid from './ChoiceGrid.vue'
import { acceptsShortcut, isEditing } from './keyboard'
import RatingBar from './RatingBar.vue'
import TypedAnswerInput from './TypedAnswerInput.vue'

const props = withDefaults(defineProps<{
  attemptId: string
  prompt: ExercisePrompt
  feedback?: ExerciseFeedback
  autoRating?: Rating
  hint?: string
  hintAvailable?: boolean
  hintLoading?: boolean
  disabled?: boolean
  submitting?: boolean
}>(), {
  hintAvailable: true,
  hintLoading: false,
  disabled: false,
  submitting: false,
})
const emit = defineEmits<{
  answered: [answer: ExerciseAnswer]
  hint: []
  giveUp: [timing: Pick<ExerciseAnswer, 'duration_ms'>]
  confirm: [rating: Rating]
  exit: []
  audio: []
}>()
const { t } = useI18n()
const id = useId()
const answer = ref('')
const sent = ref(false)
const startedAt = ref(0)
const choices = ref<InstanceType<typeof ChoiceGrid>>()
const typed = ref<InstanceType<typeof TypedAnswerInput>>()
const rating = ref<InstanceType<typeof RatingBar>>()
const busy = computed(() => props.disabled || props.submitting || props.hintLoading || sent.value)
const canAnswer = computed(() => props.prompt.input === 'choice'
  ? props.prompt.choices.some(choice => choice.id === answer.value)
  : Boolean(answer.value.trim()))

async function focusAnswer() {
  await nextTick()
  if (!busy.value) {
    choices.value?.focus()
    typed.value?.focus()
  }
}
function reset() {
  answer.value = ''
  sent.value = false
  startedAt.value = performance.now()
  void focusAnswer()
}
onMounted(reset)
watch(() => props.attemptId, reset)
watch(() => props.submitting, (value) => {
  if (!value)
    sent.value = false
})
watch(() => props.feedback, async (value) => {
  if (value) {
    sent.value = false
    await nextTick()
    void rating.value?.focus()
  }
})
function timing() {
  return {
    duration_ms: Math.max(0, Math.floor(performance.now() - startedAt.value)),
  }
}
function submit() {
  if (busy.value || props.feedback || !canAnswer.value)
    return
  sent.value = true
  emit('answered', {
    answer: answer.value,
    ...timing(),
  })
}
function requestHint() {
  if (!busy.value && !props.feedback && props.hintAvailable && props.hint === undefined)
    emit('hint')
}
function giveUp() {
  if (busy.value || props.feedback)
    return
  sent.value = true
  emit('giveUp', timing())
}
function keydown(event: KeyboardEvent) {
  if (!acceptsShortcut(event) || isEditing(event))
    return
  if (event.key.toLowerCase() === 'h') {
    event.preventDefault()
    event.stopPropagation()
    requestHint()
  }
  else if (event.key === 'Escape') {
    event.preventDefault()
    emit('exit')
  }
  else if (event.key === ' ' && event.target === event.currentTarget) {
    event.preventDefault()
    emit('audio')
  }
}
</script>

<template>
  <section
    :aria-labelledby="`${id}-prompt`" :aria-busy="submitting || hintLoading"
    tabindex="0" class="min-w-0 space-y-6 rounded-lg bg-surface p-4 pw-focus-ring sm:p-6"
    @keydown="keydown"
  >
    <slot name="progress" />
    <div :id="`${id}-prompt`" class="break-words text-center text-2xl font-semibold sm:text-3xl">
      <slot name="prompt">
        {{ prompt.text }}
      </slot>
    </div>
    <slot name="answer" :answer="answer" :disabled="busy || Boolean(feedback)" :submit="submit" :update-answer="(value: string) => answer = value">
      <ChoiceGrid
        v-if="prompt.input === 'choice'" ref="choices" v-model="answer"
        :choices="prompt.choices" :disabled="busy || Boolean(feedback)" @submit="submit"
      />
      <TypedAnswerInput
        v-else ref="typed" v-model="answer"
        :disabled="busy" :feedback="feedback" @submit="submit"
      />
    </slot>
    <p v-if="hint !== undefined" role="status" class="rounded-md bg-info-soft p-3 text-info">
      {{ t('exercise.hintLabel') }} {{ hint }}
    </p>
    <div v-if="!feedback" class="flex flex-wrap gap-3">
      <NButton size="large" type="primary" :disabled="busy || !canAnswer" :loading="submitting" @click="submit">
        {{ t('exercise.submit') }}
      </NButton>
      <NButton v-if="hintAvailable" size="large" :disabled="busy || hint !== undefined" :loading="hintLoading" @click="requestHint">
        <template #icon>
          <i-lucide-lightbulb aria-hidden="true" />
        </template>
        {{ t('exercise.hint') }}
      </NButton>
      <NButton size="large" :disabled="busy" @click="giveUp">
        {{ t('exercise.giveUp') }}
      </NButton>
    </div>
    <div v-if="feedback" role="status" class="space-y-3">
      <p class="m-0 font-semibold" :class="feedback.correct ? 'text-success' : 'text-error'">
        {{ t(feedback.correct ? 'exercise.correct' : 'exercise.incorrect') }}
      </p>
      <p v-if="prompt.input === 'choice'" class="break-words">
        {{ t('exercise.expectedAnswer') }} {{ feedback.answer }}
      </p>
      <slot name="feedback" :feedback="feedback" />
    </div>
    <RatingBar
      v-if="feedback && autoRating !== undefined" ref="rating" :key="attemptId"
      :auto-rating="autoRating" :disabled="disabled" :loading="submitting"
      @confirm="emit('confirm', $event)"
    />
    <p v-if="!feedback" class="m-0 text-sm text-muted">
      {{ t(prompt.input === 'choice' ? 'exercise.choiceShortcuts' : 'exercise.typedShortcuts') }}
    </p>
  </section>
</template>
