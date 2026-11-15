import type { OfflineData, OfflineEntry } from './offlineStorage'
import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { api } from '@/api/client'
import { minimalAttempt, offlineData, offlineEvents } from './offlineStorage'

type Answer = components['schemas']['AttemptAnswer']

export function useOfflineReview(owner: () => string, project: () => string) {
  const entries = shallowRef<OfflineEntry[]>([])
  const receipts = ref<string[]>([])
  const busy = ref(false)
  const failed = ref(false)
  const online = ref(navigator.onLine)
  const now = ref(Date.now())
  let generation = 0
  let disposed = false
  const selected = computed(() => entries.value.filter(entry => entry.attempt.project_id === project()))
  const pending = computed(() => selected.value.filter(entry => entry.answer))
  const current = computed(() => selected.value.find(entry => !entry.answer
    && !entry.failure && Date.parse(entry.attempt.expires_at) > now.value))
  const ready = computed(() => selected.value.filter(entry => !entry.answer
    && !entry.failure && Date.parse(entry.attempt.expires_at) > now.value).length)
  const state = computed(() => busy.value
    ? 'syncing'
    : failed.value || selected.value.some(entry => entry.failure === 'failed' || entry.failure === 'stale')
      ? 'failed'
      : selected.value.some(entry => entry.failure === 'expired' || Date.parse(entry.attempt.expires_at) <= now.value)
        ? 'expired'
        : online.value ? 'online' : 'offline')

  function apply(data: OfflineData) {
    entries.value = data.entries
    receipts.value = data.receipts
  }
  async function run(operation: (who: string, valid: () => boolean) => Promise<void>) {
    if (busy.value || !owner() || disposed)
      return
    const version = generation
    const who = owner()
    const valid = () => !disposed && generation === version && owner() === who
    busy.value = true
    failed.value = false
    try {
      await operation(who, valid)
    }
    catch {
      if (valid())
        failed.value = true
    }
    finally {
      if (valid())
        busy.value = false
    }
  }
  async function load() {
    await run(async (who, valid) => {
      const data = await offlineData(who)
      if (valid())
        apply(data)
    })
  }
  async function prepare() {
    await run(async (who, valid) => {
      const response = await api.POST('/api/exercise-attempts/offline', {
        body: {
          project_id: project(),
          limit: 10,
        },
      })
      if (!valid())
        return
      if (!response.data)
        throw new Error('Offline prefetch rejected')
      const attempts = response.data.attempts
      const data = await offlineData(who, (data) => {
        for (const attempt of attempts) {
          if (data.entries.some(entry => entry.attempt.id === attempt.id))
            continue
          if (data.entries.length >= 20)
            throw new Error('Offline queue full')
          if (attempt.prompt.media_id)
            throw new Error('Offline media unavailable')
          data.entries.push({
            attempt: minimalAttempt(attempt),
          })
        }
      })
      if (valid())
        apply(data)
    })
  }
  async function answer(body: Pick<Answer, 'answer' | 'duration_ms'> & { gave_up?: boolean }) {
    const id = current.value?.attempt.id
    if (!id)
      return
    await run(async (who, valid) => {
      const data = await offlineData(who, (data) => {
        const entry = data.entries.find(entry => entry.attempt.id === id)
        if (!entry || entry.answer || Date.parse(entry.attempt.expires_at) <= Date.now())
          throw new Error('Offline attempt unavailable')
        entry.answer = {
          ...body,
          client_key: crypto.randomUUID(),
        }
      })
      if (valid())
        apply(data)
    })
  }
  async function mark(who: string, id: string, failure: OfflineEntry['failure']) {
    return offlineData(who, (data) => {
      const entry = data.entries.find(entry => entry.attempt.id === id)
      if (entry)
        entry.failure = failure
    })
  }
  async function sync() {
    if (!online.value)
      return
    await run(async (who, valid) => {
      const snapshot = await offlineData(who)
      for (const saved of snapshot.entries.filter(entry => entry.answer)) {
        if (!valid())
          return
        const id = saved.attempt.id
        const params = {
          path: { attempt_id: id },
        }
        try {
          let rating = saved.rating
          if (rating === undefined) {
            const body = saved.answer!
            const graded = body.gave_up
              ? await api.POST('/api/exercise-attempts/{attempt_id}/giveup', {
                  params,
                  body: { duration_ms: body.duration_ms, client_key: body.client_key },
                })
              : await api.POST('/api/exercise-attempts/{attempt_id}/answer', {
                  params,
                  body: { answer: body.answer, duration_ms: body.duration_ms, client_key: body.client_key },
                })
            if (!valid())
              return
            if (!graded.data) {
              const status = graded.response.status
              apply(await mark(who, id, status === 410
                ? 'expired'
                : status === 409
                  ? 'stale'
                  : 'failed'))
              continue
            }
            if (graded.data.status === 'open')
              throw new Error('Missing server grade')
            rating = graded.data.auto_rating
            // Persist the confirmation stage before sending: a lost receipt response
            // must retry confirm, not re-grade a now-stale memory.
            const value = rating
            await offlineData(who, (data) => {
              const entry = data.entries.find(entry => entry.attempt.id === id)
              if (!entry)
                throw new Error('Offline answer was evicted')
              entry.rating = value
            })
          }
          const confirmed = await api.POST('/api/exercise-attempts/{attempt_id}/confirm', {
            params,
            body: { rating },
          })
          if (!valid())
            return
          if (!confirmed.data) {
            const status = confirmed.response.status
            apply(await mark(who, id, status === 410
              ? 'expired'
              : status === 409
                ? 'stale'
                : 'failed'))
            continue
          }
          if (confirmed.data.status !== 'confirmed' || confirmed.data.receipt.attempt_id !== id)
            throw new Error('Missing durable review receipt')
          apply(await offlineData(who, (data) => {
            data.entries = data.entries.filter(entry => entry.attempt.id !== id)
            if (!data.receipts.includes(id))
              data.receipts = [...data.receipts, id].slice(-20)
          }))
        }
        catch {
          if (!valid())
            return
          apply(await mark(who, id, 'failed'))
          failed.value = true
        }
      }
    })
  }
  async function discard(id: string) {
    await run(async (who, valid) => {
      const data = await offlineData(who, (data) => {
        data.entries = data.entries.filter(entry => entry.attempt.id !== id)
      })
      if (valid())
        apply(data)
    })
  }
  function connectivity() {
    online.value = navigator.onLine
    if (online.value)
      void sync()
  }
  function purged() {
    generation++
    entries.value = []
    receipts.value = []
    busy.value = false
    failed.value = true
  }
  watch(() => [
    owner(),
    project(),
  ], () => {
    generation++
    entries.value = []
    receipts.value = []
    busy.value = false
    failed.value = false
    void load()
  }, { immediate: true, flush: 'sync' })
  const timer = window.setInterval(() => {
    now.value = Date.now()
  }, 1000)
  window.addEventListener('online', connectivity)
  window.addEventListener('offline', connectivity)
  offlineEvents.addEventListener('purged', purged)
  onScopeDispose(() => {
    disposed = true
    generation++
    window.clearInterval(timer)
    window.removeEventListener('online', connectivity)
    window.removeEventListener('offline', connectivity)
    offlineEvents.removeEventListener('purged', purged)
  })
  return {
    selected,
    pending,
    current,
    ready,
    receipts,
    busy,
    online,
    state,
    failed,
    load,
    prepare,
    answer,
    sync,
    discard,
  }
}
