import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref } from 'vue'
import { activateOfflineOwner, clearOfflineOwner, minimalAttempt, offlineData } from './offlineStorage'
import { confirmed, graded, open, project, success } from './reviewTestHarness'
import { useOfflineReview } from './useOfflineReview'
import 'fake-indexeddb/auto'

const client = vi.hoisted(() => ({
  POST: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
const who = ref('alice')
let stop: (() => void) | undefined
const saved = () => offlineData(who.value)
async function seed(id = open.id) {
  await offlineData(who.value, data => data.entries.push({
    attempt: minimalAttempt({ ...open, id }),
  }))
}
async function setup() {
  const scope = effectScope()
  stop = () => scope.stop()
  const state = scope.run(() => useOfflineReview(() => who.value, () => project.id))!
  await vi.waitFor(() => expect(state.busy.value).toBe(false))
  return state
}
beforeEach(async () => {
  vi.resetAllMocks()
  Object.defineProperty(navigator, 'onLine', { value: true, configurable: true })
  who.value = 'alice'
  await clearOfflineOwner('alice')
  await clearOfflineOwner('bob')
  activateOfflineOwner('alice')
})
afterEach(() => {
  stop?.()
  vi.unstubAllGlobals()
})

describe('owner-partitioned offline queue', () => {
  it('does not send an expired prompt or pretend a failed storage write succeeded', async () => {
    await offlineData('alice', data => data.entries.push({
      attempt: {
        ...minimalAttempt(open),
        expires_at: '2000-01-01T00:00:00Z',
      },
    }))
    const state = await setup()
    expect(state.current.value).toBeUndefined()
    expect(state.state.value).toBe('expired')
    await state.answer({ answer: 'late', duration_ms: 10 })
    expect(client.POST).not.toHaveBeenCalled()
    vi.stubGlobal('indexedDB', undefined)
    await state.load()
    expect(state.failed.value).toBe(true)
    expect(state.receipts.value).toEqual([])
  })

  it('uses the existing give-up grader and does not send the local discriminator to the API', async () => {
    await seed()
    const state = await setup()
    await state.answer({ answer: '', duration_ms: 20, gave_up: true })
    client.POST.mockResolvedValueOnce(success(graded)).mockResolvedValueOnce(success(confirmed))
    await state.sync()
    expect(client.POST.mock.calls[0]![0]).toBe('/api/exercise-attempts/{attempt_id}/giveup')
    expect(client.POST.mock.calls[0]![1].body).toEqual({
      duration_ms: 20,
      client_key: expect.any(String),
    })
    expect(state.receipts.value).toEqual([open.id])
  })
  it('stores only prompt data, not hints, feedback, answer keys or credentials', async () => {
    const unsafe = {
      ...open,
      hint: 'private hint',
      feedback: graded.feedback,
      private: { answer: 'secret' },
    }
    client.POST.mockResolvedValue(success({
      attempts: [unsafe],
    }))
    const state = await setup()
    await state.prepare()
    const value = JSON.stringify(await saved())
    expect(value).not.toMatch(/secret|private hint|feedback|token|accepted_forms/)
    expect(state.current.value?.attempt.prompt).toEqual({ text: open.prompt.text, input: 'choice', choices: open.prompt.choices })
  })

  it('persists offline answers, counts only receipts, and safely retries a lost grade response', async () => {
    await seed()
    const state = await setup()
    Object.defineProperty(navigator, 'onLine', { value: false })
    window.dispatchEvent(new Event('offline'))
    await state.answer({ answer: 'opaque-bank', duration_ms: 20 })
    expect(state.state.value).toBe('offline')
    expect(state.receipts.value).toEqual([])
    const identity = (await saved()).entries[0]!.answer!.client_key
    stop?.()
    const restored = await setup()
    expect(restored.pending.value).toHaveLength(1)
    client.POST.mockRejectedValueOnce(new Error('lost grade'))
    Object.defineProperty(navigator, 'onLine', { value: true })
    window.dispatchEvent(new Event('online'))
    await vi.waitFor(() => expect(restored.state.value).toBe('failed'))
    expect((await saved()).entries[0]!.answer!.client_key).toBe(identity)
    client.POST.mockImplementation((url: string) => Promise.resolve(success(url.endsWith('/confirm')
      ? confirmed
      : graded)))
    await restored.sync()
    expect(restored.receipts.value).toEqual([open.id])
    expect((await saved()).entries).toEqual([])
    expect(client.POST.mock.calls.filter(([url]) => url.endsWith('/answer')).every(([, options]) => options.body.client_key === identity)).toBe(true)
    await restored.sync()
    expect(restored.receipts.value).toHaveLength(1)
  })

  it('persists confirm stage without an answer key and recovers a lost receipt response', async () => {
    await seed()
    const state = await setup()
    await state.answer({ answer: 'opaque-bank', duration_ms: 20 })
    client.POST.mockResolvedValueOnce(success(graded)).mockRejectedValueOnce(new Error('lost receipt'))
    await state.sync()
    const data = await saved()
    expect(data.entries[0]!.rating).toBe(3)
    expect(JSON.stringify(data)).not.toContain('feedback')
    client.POST.mockResolvedValue(success(confirmed))
    await state.sync()
    expect(client.POST.mock.calls.map(([url]) => url)).toEqual([
      '/api/exercise-attempts/{attempt_id}/answer',
      '/api/exercise-attempts/{attempt_id}/confirm',
      '/api/exercise-attempts/{attempt_id}/confirm',
    ])
    expect(state.receipts.value).toEqual([open.id])
  })

  it('retains expired/stale answers and syncs unrelated queued work after a partial failure', async () => {
    await seed()
    await seed('second')
    const state = await setup()
    await state.answer({ answer: 'first', duration_ms: 10 })
    await state.answer({ answer: 'second', duration_ms: 10 })
    client.POST.mockResolvedValueOnce({
      response: { status: 410 },
    })
      .mockResolvedValueOnce(success({ ...graded, id: 'second' }))
      .mockResolvedValueOnce(success({
        ...confirmed,
        id: 'second',
        receipt: { ...confirmed.receipt, attempt_id: 'second' },
      }))
    await state.sync()
    expect(state.state.value).toBe('expired')
    expect(state.receipts.value).toEqual(['second'])
    expect((await saved()).entries[0]!.answer!.answer).toBe('first')
    client.POST.mockResolvedValue({
      response: { status: 409 },
    })
    await state.sync()
    expect(state.state.value).toBe('failed')
    expect((await saved()).entries).toHaveLength(1)
  })

  it('clears logout/account data, ignores late responses, and does not expose another owner', async () => {
    await seed()
    const state = await setup()
    let finish!: (value: unknown) => void
    client.POST.mockImplementation(() => new Promise((resolve) => {
      finish = resolve
    }))
    const loading = state.prepare()
    await clearOfflineOwner('alice')
    who.value = 'bob'
    activateOfflineOwner('bob')
    finish(success({
      attempts: [open],
    }))
    await loading
    await flushPromises()
    expect(state.selected.value).toEqual([])
    expect((await offlineData('bob')).entries).toEqual([])
    await expect(offlineData('alice')).rejects.toThrow()
    activateOfflineOwner('alice')
    expect((await offlineData('alice')).entries).toEqual([])
  })

  it('shows empty recovery after eviction, rejects missing media and enforces the local bound', async () => {
    await seed()
    const state = await setup()
    await offlineData('alice', (data) => {
      data.entries = []
    })
    await state.load()
    expect(state.selected.value).toEqual([])
    client.POST.mockResolvedValue(success({
      attempts: [
        {
          ...open,
          prompt: { ...open.prompt, media_id: 'missing' },
        },
      ],
    }))
    await state.prepare()
    expect(state.state.value).toBe('failed')
    expect((await saved()).entries).toEqual([])
    client.POST.mockResolvedValue(success({
      attempts: Array.from({ length: 21 }, (_, index) => ({ ...open, id: `id${index}` })),
    }))
    await state.prepare()
    expect(state.state.value).toBe('failed')
    expect((await saved()).entries).toEqual([])
  })
})
