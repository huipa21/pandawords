<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import EmptyState from '@/components/app/EmptyState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import ExerciseShell from '@/components/exercise/ExerciseShell.vue'
import ReviewProgress from '@/components/exercise/ReviewProgress.vue'
import AudioButton from '@/components/word/AudioButton.vue'
import ProtectedImage from '@/features/words/ProtectedImage.vue'
import { usePronunciation } from '@/features/words/usePronunciation'
import { useAuthStore } from '@/stores/auth'
import { useReviewSession } from './useReviewSession'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const projectId = () => String(route.params.id ?? '')
const { attempt, plan, busy, error, pending, done, active, locked, submit, hint, retry, restart } = useReviewSession(
  () => auth.user?.id ?? '',
  projectId,
)
const audio = usePronunciation(() => attempt.value?.id ?? '')
const graded = computed(() => attempt.value?.status === 'graded'
  ? attempt.value
  : undefined)
const terminal = computed(() => error.value && ['stale', 'expired', 'unavailable'].includes(error.value))
const showExit = ref(false)
let resolveExit: ((leave: boolean) => void) | undefined
function guard() {
  if (!active.value && !pending.value && !busy.value)
    return true
  showExit.value = true
  return new Promise<boolean>((resolve) => {
    resolveExit?.(false)
    resolveExit = resolve
  })
}
function settleExit(leave: boolean) {
  showExit.value = false
  resolveExit?.(leave)
  resolveExit = undefined
}
onBeforeRouteLeave(guard)
onBeforeRouteUpdate(guard)
function beforeUnload(event: BeforeUnloadEvent) {
  if (active.value || pending.value || busy.value)
    event.preventDefault()
}
window.addEventListener('beforeunload', beforeUnload)
onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', beforeUnload)
  resolveExit?.(false)
})
function exit() {
  void router.push({
    name: 'project',
    params: {
      id: projectId(),
    },
  })
}
function play() {
  if (attempt.value?.exercise !== 'image2word' && attempt.value?.prompt.media_id)
    void audio.play(attempt.value.prompt.media_id)
}
</script>

<template>
  <section class="mx-auto w-full max-w-3xl space-y-6" data-testid="review-session">
    <PageHeader :title="t('session.title')">
      <template #actions>
        <NButton size="large" data-testid="review-exit" @click="exit">
          {{ t('session.exit') }}
        </NButton>
      </template>
    </PageHeader>
    <ReviewProgress
      :done="done" :remaining="plan?.queue_total ?? (active ? 1 : 0)"
      :new-count="plan?.today.new ?? 0" :review-count="plan?.today.reviews ?? 0"
    />
    <div v-if="busy && (!attempt || attempt.status === 'confirmed')" role="status" :aria-label="t('common.loading')" data-testid="review-loading">
      <NSkeleton text :repeat="4" />
    </div>
    <NAlert v-if="error" type="warning" role="alert" data-testid="review-error" :data-error="error">
      <p>{{ t(`session.errors.${error}`) }}</p>
      <NButton v-if="terminal" size="large" :disabled="busy" data-testid="review-restart" @click="restart">
        {{ t('session.restart') }}
      </NButton>
      <NButton v-else-if="error !== 'hintUnavailable'" size="large" :loading="busy" data-testid="review-retry" @click="retry">
        {{ t('common.retry') }}
      </NButton>
    </NAlert>
    <ExerciseShell
      v-if="attempt && attempt.status !== 'confirmed'" :key="attempt.id"
      :attempt-id="attempt.id" :prompt="attempt.prompt"
      :feedback="graded?.feedback" :auto-rating="graded?.auto_rating"
      :hint="attempt.hint ?? undefined" :hint-available="error !== 'hintUnavailable'"
      :hint-loading="busy && !pending" :submitting="busy && Boolean(pending)" :disabled="locked"
      data-testid="review-exercise" :data-attempt-id="attempt.id" :data-status="attempt.status"
      @answered="submit({ action: 'answer', body: $event })"
      @give-up="submit({ action: 'giveup', body: $event })"
      @confirm="submit({ action: 'confirm', body: { rating: $event } })"
      @hint="hint" @exit="exit" @audio="play"
    >
      <template #prompt>
        <span>{{ attempt.exercise === 'image2word' ? t('session.imagePrompt') : attempt.prompt.text }}</span>
        <div v-if="attempt.exercise === 'image2word' && attempt.prompt.media_id" class="mt-4 grid gap-3" data-testid="review-image">
          <ProtectedImage :media-id="attempt.prompt.media_id" />
          <p v-if="attempt.prompt.media_attribution" class="text-sm text-muted" data-testid="review-image-attribution">
            {{ t('session.imageAttribution', { attribution: attempt.prompt.media_attribution }) }}
          </p>
        </div>
        <div v-else-if="attempt.prompt.media_id" class="mt-4 flex flex-wrap items-center justify-center gap-3">
          <AudioButton
            :playback-state="audio.playing.value ? 'playing' : 'stopped'"
            :disabled="audio.loading.value" @play="play"
          />
          <span v-if="audio.failed.value" role="status" class="text-sm text-error" data-testid="review-audio-error">
            {{ t('session.audioUnavailable') }}
          </span>
        </div>
        <p v-else-if="!attempt.prompt.text" role="status" class="text-sm text-error">
          {{ t('session.audioUnavailable') }}
        </p>
      </template>
      <template #feedback>
        <p v-if="graded" class="text-sm text-muted">
          {{ t('session.timing', { duration: graded.duration_ms, elapsed: graded.server_elapsed_ms }) }}
        </p>
      </template>
    </ExerciseShell>
    <EmptyState
      v-else-if="!busy && !error && plan && !plan.queue.length"
      :title-key="done ? 'session.complete' : 'session.empty'"
      desc-key="session.emptyDescription" data-testid="review-empty"
    >
      <template #action>
        <NButton size="large" @click="retry">
          {{ t('study.refresh') }}
        </NButton>
      </template>
    </EmptyState>
    <NModal
      :show="showExit" preset="dialog" :title="t('session.leaveTitle')"
      :content="t('session.leaveDescription')"
      :positive-text="t('session.exit')" :negative-text="t('session.stay')"
      :mask-closable="false" @positive-click="settleExit(true)"
      @negative-click="settleExit(false)" @close="settleExit(false)"
      @update:show="(value: boolean) => !value && settleExit(false)"
    />
  </section>
</template>
