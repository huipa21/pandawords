import type { PendingReview, ReviewSession } from './reviewSessionStorage'
import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { api } from '@/api/client'
import { readReviewSession, reviewSessionKey, writeReviewSession } from './reviewSessionStorage'

type Attempt = components['schemas']['AttemptRead']
type Plan = components['schemas']['StudyPlanRead']
type Failure = 'recoverable' | 'unusable' | 'expired' | 'stale' | 'unavailable' | 'storage' | 'hintUnavailable'

export function useReviewSession(owner: () => string, project: () => string) {
  const attempt = shallowRef<Attempt>()
  const plan = shallowRef<Plan>()
  const busy = ref(false)
  const error = ref<Failure>()
  const pending = shallowRef<PendingReview>()
  const done = ref(0)
  let session: ReviewSession = { completed: [] }
  let generation = 0
  let key = ''
  let loaded = false
  let disposed = false
  const active = computed(() => Boolean(attempt.value && attempt.value.status !== 'confirmed'))
  const locked = computed(() => busy.value || Boolean(pending.value) || Boolean(error.value && error.value !== 'hintUnavailable'))

  function save() {
    try {
      writeReviewSession(key, session)
      pending.value = session.pending
      done.value = session.completed.length
      return true
    }
    catch {
      error.value = 'storage'
      return false
    }
  }
  function failed(value: unknown, status: number) {
    const code = typeof value === 'object' && value && 'code' in value
      ? value.code
      : ''
    error.value = code === 'exercise.no_usable'
      ? 'unusable'
      : code === 'exercise.hint_unavailable'
        ? 'hintUnavailable'
        : status === 410
          ? 'expired'
          : status === 409
            ? 'stale'
            : status === 403 || status === 404
              ? 'unavailable'
              : 'recoverable'
  }
  async function accept(data: Attempt) {
    if (data.project_id !== project()) {
      error.value = 'unavailable'
      return
    }
    attempt.value = data
    session.attemptId = data.id
    if (data.status === 'confirmed') {
      if (!session.completed.includes(data.id))
        session.completed.push(data.id)
      session.attemptId = undefined
      session.pending = undefined
      if (save())
        await queue()
      return
    }
    if (data.status === 'graded' && session.pending?.action !== 'confirm')
      session.pending = undefined
    save()
  }
  async function queue() {
    const current = generation
    const result = await api.GET('/api/projects/{id}/study-plan', {
      params: {
        path: {
          id: project(),
        },
        query: { limit: 1, offset: 0 },
      },
    })
    if (current !== generation)
      return
    if (!result.data) {
      failed(result.error, result.response.status)
      return
    }
    plan.value = result.data
    attempt.value = undefined
    const item = result.data.queue[0]
    if (!item)
      return
    const issued = await api.POST('/api/exercise-attempts', {
      body: {
        project_id: project(),
        sense_id: item.memory.sense_id,
      },
    })
    if (current !== generation)
      return
    if (issued.data)
      await accept(issued.data)
    else
      failed(issued.error, issued.response.status)
  }
  async function run(operation: () => Promise<void>) {
    if (busy.value || disposed)
      return
    const current = generation
    busy.value = true
    error.value = undefined
    try {
      await operation()
    }
    catch {
      if (current === generation && error.value !== 'storage')
        error.value = 'recoverable'
    }
    finally {
      if (current === generation)
        busy.value = false
    }
  }
  async function restore() {
    const current = generation
    if (!session.attemptId) {
      await queue()
      return
    }
    const result = await api.GET('/api/exercise-attempts/{attempt_id}', {
      params: {
        path: { attempt_id: session.attemptId },
      },
    })
    if (current !== generation)
      return
    if (result.data) {
      await accept(result.data)
      if (result.data.status !== 'confirmed' && current === generation) {
        const progress = await api.GET('/api/projects/{id}/study-plan', {
          params: {
            path: {
              id: project(),
            },
            query: { limit: 1, offset: 0 },
          },
        })
        if (current !== generation)
          return
        if (progress.data)
          plan.value = progress.data
        else
          failed(progress.error, progress.response.status)
      }
      if (session.pending && !error.value)
        error.value = 'recoverable'
    }
    else {
      failed(result.error, result.response.status)
    }
  }
  async function send() {
    const request = session.pending
    const id = session.attemptId
    if (!request || !id)
      return
    const current = generation
    const params = {
      path: { attempt_id: id },
    }
    const result = request.action === 'answer'
      ? await api.POST('/api/exercise-attempts/{attempt_id}/answer', { params, body: request.body })
      : request.action === 'giveup'
        ? await api.POST('/api/exercise-attempts/{attempt_id}/giveup', { params, body: request.body })
        : await api.POST('/api/exercise-attempts/{attempt_id}/confirm', { params, body: request.body })
    if (current !== generation)
      return
    if (result.data) {
      // Only a durable receipt may clear a pending confirmation.
      if ((request.action === 'confirm' && result.data.status !== 'confirmed') || result.data.status === 'open') {
        error.value = 'recoverable'
        return
      }
      session.pending = undefined
      await accept(result.data)
    }
    else {
      failed(result.error, result.response.status)
    }
  }
  function submit(request: PendingReview) {
    if (locked.value || !attempt.value || (request.action === 'confirm'
      ? attempt.value.status !== 'graded'
      : attempt.value.status !== 'open')) {
      return
    }
    session.pending = request
    if (save())
      void run(send)
  }
  function hint() {
    if (locked.value || attempt.value?.status !== 'open' || attempt.value.hint_used)
      return
    void run(async () => {
      const current = generation
      const result = await api.POST('/api/exercise-attempts/{attempt_id}/hint', {
        params: {
          path: { attempt_id: attempt.value!.id },
        },
      })
      if (current !== generation)
        return
      if (result.data)
        await accept(result.data)
      else
        failed(result.error, result.response.status)
    })
  }
  function retry() {
    if (error.value === 'storage') {
      if (!loaded) {
        try {
          session = readReviewSession(key)
          loaded = true
          pending.value = session.pending
          done.value = session.completed.length
        }
        catch {
          return
        }
        void run(restore)
        return
      }
      if (!save())
        return
    }
    void run(session.pending ? send : restore)
  }
  function restart() {
    if (busy.value)
      return
    session.attemptId = undefined
    session.pending = undefined
    if (save()) {
      attempt.value = undefined
      void run(queue)
    }
  }
  watch(() => [
    owner(),
    project(),
  ], () => {
    generation++
    busy.value = false
    attempt.value = undefined
    plan.value = undefined
    pending.value = undefined
    error.value = undefined
    done.value = 0
    session = { completed: [] }
    loaded = false
    key = reviewSessionKey(owner(), project())
    if (!owner() || !project())
      return
    try {
      session = readReviewSession(key)
      loaded = true
      pending.value = session.pending
      done.value = session.completed.length
      void run(restore)
    }
    catch {
      error.value = 'storage'
    }
  }, { immediate: true })
  onScopeDispose(() => {
    disposed = true
    generation++
  })
  return {
    attempt,
    plan,
    busy,
    error,
    pending,
    done,
    active,
    locked,
    submit,
    hint,
    retry,
    restart,
  }
}
