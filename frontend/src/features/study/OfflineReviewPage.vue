<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import PageHeader from '@/components/app/PageHeader.vue'
import ExerciseShell from '@/components/exercise/ExerciseShell.vue'
import { useAuthStore } from '@/stores/auth'
import { useOfflineReview } from './useOfflineReview'

const auth = useAuthStore()
const route = useRoute()
const { t } = useI18n()
const { selected, pending, current, ready, receipts, busy, online, state, failed, load, prepare, answer, sync, discard } = useOfflineReview(
  () => auth.user?.id ?? '',
  () => String(route.params.id ?? ''),
)
const removing = ref<string>()
function remove() {
  const id = removing.value
  removing.value = undefined
  if (id)
    void discard(id)
}
</script>

<template>
  <section class="mx-auto w-full max-w-3xl space-y-6" data-testid="offline-review">
    <PageHeader :title="t('offline.title')" />
    <p class="text-muted">
      {{ t('offline.policy') }}
    </p>
    <p role="status" aria-live="polite" :data-state="state">
      {{ t(`offline.states.${state}`) }}
      {{ t('offline.counts', { ready, pending: pending.length, done: receipts.length }) }}
    </p>
    <NAlert v-if="failed" type="warning" role="alert">
      {{ t('offline.failure') }}
    </NAlert>
    <div class="flex flex-wrap gap-3">
      <NButton size="large" :disabled="busy || !online" @click="prepare">
        {{ t('offline.prepare') }}
      </NButton>
      <NButton size="large" :disabled="busy || !online || !pending.length" @click="sync">
        {{ t('offline.sync') }}
      </NButton>
      <NButton size="large" :disabled="busy" @click="load">
        {{ t('offline.reload') }}
      </NButton>
    </div>
    <p v-if="!selected.length" role="status">
      {{ t('offline.empty') }}
    </p>
    <ExerciseShell
      v-if="current" :key="current.attempt.id" :attempt-id="current.attempt.id"
      :prompt="current.attempt.prompt" :hint-available="false" :disabled="busy"
      :submitting="busy" @answered="answer"
      @give-up="({ duration_ms }) => answer({ answer: '', duration_ms, gave_up: true })"
    />
    <ul class="list-none space-y-3 p-0">
      <li v-for="entry in selected.filter(item => item.answer || item.failure || Date.parse(item.attempt.expires_at) <= Date.now())" :key="entry.attempt.id" class="rounded-lg bg-surface p-4">
        <p>{{ entry.attempt.prompt.text }}</p>
        <p v-if="entry.answer" class="break-words">
          {{ t('offline.savedAnswer', { answer: entry.answer.answer }) }}
        </p>
        <p v-if="entry.failure" role="status">
          {{ t(`offline.recovery.${entry.failure}`) }}
        </p>
        <p v-else-if="Date.parse(entry.attempt.expires_at) <= Date.now()" role="status">
          {{ t('offline.recovery.expired') }}
        </p>
        <p class="text-sm text-muted">
          {{ t('offline.expires', { at: entry.attempt.expires_at }) }}
        </p>
        <NButton size="large" :disabled="busy" @click="removing = entry.attempt.id">
          {{ t('offline.discard') }}
        </NButton>
      </li>
    </ul>
    <NModal
      :show="Boolean(removing)" preset="dialog" :title="t('offline.discard')"
      :content="t('offline.discardWarning')" :positive-text="t('offline.discard')"
      :negative-text="t('common.cancel')" @positive-click="remove"
      @negative-click="removing = undefined" @close="removing = undefined"
    />
  </section>
</template>
