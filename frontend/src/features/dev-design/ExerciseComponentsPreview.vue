<script setup lang="ts">
import type { ExerciseFeedback, Rating } from '@/components/exercise/types'
import { NButton } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ExerciseShell from '@/components/exercise/ExerciseShell.vue'
import ReviewProgress from '@/components/exercise/ReviewProgress.vue'
import TypedAnswerInput from '@/components/exercise/TypedAnswerInput.vue'

const { t } = useI18n()
const feedback = ref<ExerciseFeedback>()
const hint = ref<string>()
const attempt = ref(0)
const confirmed = ref<Rating>()
const prompt = computed(() => ({
  text: t('exercise.preview.prompt'),
  input: 'choice' as const,
  choices: ['bank', 'river', 'tree', 'book'].map(id => ({
    id,
    label: t(`exercise.preview.${id}`),
  })),
}))
function grade() {
  feedback.value = {
    correct: true,
    answer: t('exercise.preview.bank'),
  }
}
function reset() {
  feedback.value = undefined
  hint.value = undefined
  confirmed.value = undefined
  attempt.value++
}
</script>

<template>
  <section class="min-w-0 space-y-4">
    <h4 class="text-base font-semibold">
      {{ t('exercise.preview.title') }}
    </h4>
    <p class="text-sm text-muted">
      {{ t('exercise.preview.simulation') }}
    </p>
    <h5 class="text-base font-medium">
      {{ t('exercise.preview.ready') }}
    </h5>
    <ExerciseShell
      :attempt-id="`preview-${attempt}`" :prompt="prompt"
      :feedback="feedback" :auto-rating="3" :hint="hint" :disabled="Boolean(confirmed)"
      @answered="grade" @give-up="feedback = { correct: false, answer: t('exercise.preview.bank') }"
      @hint="hint = t('exercise.preview.hint')" @confirm="confirmed = $event"
    >
      <template #progress>
        <ReviewProgress :done="3" :remaining="7" :new-count="2" :review-count="5" />
      </template>
    </ExerciseShell>
    <p v-if="confirmed" role="status">
      {{ t('exercise.preview.confirmed', { rating: confirmed }) }}
    </p>
    <NButton size="large" @click="reset">
      {{ t('exercise.preview.reset') }}
    </NButton>
    <h5 class="text-base font-medium">
      {{ t('exercise.preview.recall') }}
    </h5>
    <ExerciseShell
      attempt-id="recall-feedback"
      :prompt="{ text: t('exercise.preview.recallPrompt'), input: 'text', choices: [] }"
      :feedback="{ correct: false, answer: 'bank' }" :auto-rating="1"
      :hint="t('exercise.preview.hint')"
    >
      <template #answer>
        <TypedAnswerInput model-value="banck" :feedback="{ correct: false, answer: 'bank' }" />
      </template>
    </ExerciseShell>
    <h5 class="text-base font-medium">
      {{ t('exercise.preview.loading') }}
    </h5>
    <ExerciseShell attempt-id="submitting" :prompt="{ ...prompt, choices: prompt.choices.slice(0, 2) }" submitting />
  </section>
</template>
