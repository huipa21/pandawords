<script setup lang="ts">
import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'

const props = withDefaults(defineProps<{
  jobs: components['schemas']['JobRead'][]
  active?: boolean
}>(), { active: true })
const emit = defineEmits<{
  'update:jobs': [jobs: components['schemas']['JobRead'][]]
  'settled': [jobs: components['schemas']['JobRead'][]]
}>()
const { t } = useI18n()
const current = ref(props.jobs)
const errors = ref<string[]>([])
const refreshing = ref(false)
const pending = computed(() => current.value.filter(job => job.status === 'queued' || job.status === 'running'))
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
let generation = 0
let notified = false

function stop() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  refreshing.value = false
}
function reconcile(jobs: components['schemas']['JobRead'][]) {
  const previous = new Map(current.value.map(job => [job.id, job]))
  current.value = jobs.map((job) => {
    const known = previous.get(job.id)
    return known && (known.status === 'done' || known.status === 'failed')
      ? known
      : job
  })
}
async function refresh(retry = false) {
  if (!props.active || refreshing.value)
    return
  clearTimeout(timer)
  if (retry)
    errors.value = []
  if (current.value.length && !pending.value.length && !notified) {
    notified = true
    emit('settled', current.value)
  }
  const targets = pending.value.filter(job => !errors.value.includes(job.id))
  if (!targets.length)
    return
  const run = generation
  controller = new AbortController()
  const signal = controller.signal
  refreshing.value = true
  await Promise.all(targets.map(async (job) => {
    try {
      const result = await api.GET('/api/jobs/{id}', {
        params: {
          path: { id: job.id },
        },
        signal,
      })
      if (run !== generation)
        return
      if (result.data) {
        current.value = current.value.map(item => item.id === job.id
          ? result.data
          : item)
        emit('update:jobs', current.value)
      }
      else {
        errors.value = [...errors.value, job.id]
      }
    }
    catch {
      if (run === generation)
        errors.value = [...errors.value, job.id]
    }
  }))
  if (run !== generation)
    return
  refreshing.value = false
  if (!pending.value.length && !notified) {
    notified = true
    emit('settled', current.value)
  }
  if (pending.value.some(job => !errors.value.includes(job.id)))
    timer = setTimeout(refresh, 1500)
}
watch(() => props.jobs, reconcile, { flush: 'sync' })
watch([
  () => props.active,
  () => props.jobs.map(job => job.id).join('\0'),
], () => {
  stop()
  reconcile(props.jobs)
  errors.value = []
  notified = false
  void refresh()
}, { immediate: true, flush: 'sync' })
onScopeDispose(stop)
</script>

<template>
  <section v-if="current.length" class="space-y-3" :aria-label="t('jobs.title')" data-testid="job-status">
    <h3 class="m-0 text-base font-semibold">
      {{ t('jobs.title') }}
    </h3>
    <ul class="m-0 list-none space-y-3 p-0" aria-live="polite">
      <li v-for="job in current" :key="job.id" class="space-y-2 break-words" :data-job-id="job.id" :data-job-status="job.status">
        <div class="flex flex-wrap items-center gap-2">
          <NTag :type="job.status === 'failed' ? 'error' : job.status === 'done' ? 'success' : 'info'">
            {{ t(`jobs.${job.status}`) }}
          </NTag>
          <span class="text-sm text-muted">{{ job.id }}</span>
        </div>
        <p v-if="job.status === 'failed'" role="alert" class="m-0 text-sm text-error">
          {{ t('jobs.failedHelp') }}
        </p>
        <p v-if="errors.includes(job.id)" role="alert" class="m-0 text-sm text-error">
          {{ t('jobs.pollError') }}
        </p>
      </li>
    </ul>
    <NButton v-if="errors.length && active" size="large" :loading="refreshing" :disabled="refreshing" data-testid="job-retry" @click="refresh(true)">
      {{ t('common.retry') }}
    </NButton>
  </section>
</template>
