import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { reviewSessionKey } from './reviewSessionStorage'
import { confirmed, empty, graded, open, project, queued, success } from './reviewTestHarness'
import { useReviewSession } from './useReviewSession'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let stop: (() => void) | undefined
const owner = ref('user:first')
const projectId = ref(project.id)
const key = () => reviewSessionKey(owner.value, projectId.value)
async function setup() {
  const scope = effectScope()
  stop = () => scope.stop()
  const session = scope.run(() => useReviewSession(() => owner.value, () => projectId.value))!
  await flushPromises()
  return session
}
beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  owner.value = 'user:first'
  projectId.value = project.id
  client.GET.mockImplementation((url: string) => Promise.resolve(success(url.includes('study-plan')
    ? queued
    : graded)))
  client.POST.mockResolvedValue(success(open))
})
afterEach(() => stop?.())

describe('durable review recovery', () => {
  it('resumes pending manual confirmation with its original rating rather than the auto suggestion', async () => {
    sessionStorage.setItem(key(), JSON.stringify({
      completed: [],
      attemptId: open.id,
      pending: {
        action: 'confirm',
        body: { rating: 4 },
      },
    }))
    const state = await setup()
    expect(state.attempt.value?.status).toBe('graded')
    expect(state.plan.value?.queue_total).toBe(1)
    expect(state.error.value).toBe('recoverable')
    expect(client.POST).not.toHaveBeenCalled()
    client.POST.mockResolvedValue(success(confirmed))
    client.GET.mockResolvedValue(success(empty))
    state.retry()
    state.retry()
    await flushPromises()
    expect(client.POST).toHaveBeenCalledExactlyOnceWith('/api/exercise-attempts/{attempt_id}/confirm', {
      params: {
        path: { attempt_id: open.id },
      },
      body: { rating: 4 },
    })
    expect(state.done.value).toBe(1)
    expect(state.attempt.value).toBeUndefined()
  })

  it('does not reapply a confirmed review when refreshing progress fails', async () => {
    const state = await setup()
    client.POST.mockResolvedValue(success(graded))
    state.submit({
      action: 'answer',
      body: { answer: 'opaque-bank', duration_ms: 12 },
    })
    await flushPromises()
    client.POST.mockResolvedValue(success(confirmed))
    client.GET.mockRejectedValueOnce(new Error('queue offline'))
    state.submit({
      action: 'confirm',
      body: { rating: 4 },
    })
    await flushPromises()
    expect(state.done.value).toBe(1)
    expect(state.error.value).toBe('recoverable')
    const posts = client.POST.mock.calls.length
    client.GET.mockResolvedValue(success(empty))
    state.retry()
    await flushPromises()
    expect(client.POST).toHaveBeenCalledTimes(posts)
    expect(state.done.value).toBe(1)
  })

  it('never treats a non-receipt confirmation response as completion', async () => {
    sessionStorage.setItem(key(), JSON.stringify({ completed: [], attemptId: open.id }))
    const state = await setup()
    client.POST.mockResolvedValue(success(graded))
    state.submit({
      action: 'confirm',
      body: { rating: 2 },
    })
    state.submit({
      action: 'confirm',
      body: { rating: 4 },
    })
    await flushPromises()
    expect(state.done.value).toBe(0)
    expect(state.pending.value).toEqual({
      action: 'confirm',
      body: { rating: 2 },
    })
    expect(state.error.value).toBe('recoverable')
    expect(client.POST).toHaveBeenCalledTimes(1)
  })

  it('discards late issuance after the owner changes and never writes it to the new owner scope', async () => {
    let finish!: (value: ReturnType<typeof success>) => void
    client.POST.mockImplementationOnce(() => new Promise(resolve => finish = resolve))
    const state = await setup()
    owner.value = 'user:second'
    client.POST.mockResolvedValue(success({ ...open, id: 'attempt:second' }))
    await flushPromises()
    finish(success(open))
    await flushPromises()
    expect(state.attempt.value?.id).toBe('attempt:second')
    expect(JSON.parse(sessionStorage.getItem(key())!).attemptId).toBe('attempt:second')
    expect(sessionStorage.getItem(reviewSessionKey('user:first', project.id))).toBeNull()
  })

  it('does not use another project session and ignores responses after disposal', async () => {
    sessionStorage.setItem(reviewSessionKey(owner.value, 'project:other'), JSON.stringify({ completed: [], attemptId: 'attempt:other' }))
    let finish!: (value: ReturnType<typeof success>) => void
    client.POST.mockImplementationOnce(() => new Promise(resolve => finish = resolve))
    await setup()
    expect(client.GET).toHaveBeenCalledTimes(1)
    stop?.()
    finish(success(open))
    await flushPromises()
    expect(sessionStorage.getItem(key())).toBeNull()
  })

  it('re-reads storage after a temporary read failure without erasing an uncertain confirmation', async () => {
    sessionStorage.setItem(key(), JSON.stringify({
      completed: [],
      attemptId: open.id,
      pending: {
        action: 'confirm',
        body: { rating: 4 },
      },
    }))
    const read = vi.spyOn(sessionStorage, 'getItem').mockImplementationOnce(() => {
      throw new Error('temporarily blocked')
    })
    const state = await setup()
    expect(state.error.value).toBe('storage')
    expect(client.GET).not.toHaveBeenCalled()
    state.retry()
    await flushPromises()
    expect(state.attempt.value?.id).toBe(open.id)
    expect(state.pending.value).toEqual({
      action: 'confirm',
      body: { rating: 4 },
    })
    expect(client.POST).not.toHaveBeenCalled()
    read.mockRestore()
  })
})
