import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import ExerciseShell from '@/components/exercise/ExerciseShell.vue'
import { reviewSessionKey } from './reviewSessionStorage'
import { button, confirmed, empty, failure, graded, open, project, queued, setup, success } from './reviewTestHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}))
const useAuth = vi.hoisted(() => vi.fn())
vi.mock('@/api/client', () => ({ api: client }))
vi.mock('@/stores/auth', () => ({ useAuthStore: useAuth }))
const auth = reactive({
  user: { id: 'user:learner' },
})
const key = () => reviewSessionKey(auth.user.id, project.id)
const path = `/projects/${project.id}/review`
let cleanup: (() => void) | undefined
async function render(locale: 'en' | 'zh-CN' = 'en') {
  const app = await setup(path, locale)
  cleanup = app.cleanup
  return app
}
async function answer() {
  await button('1. bank').trigger('click')
  await button('Submit answer').trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  auth.user.id = 'user:learner'
  useAuth.mockReturnValue(auth)
  client.GET.mockImplementation((url: string) => Promise.resolve(success(
    url === '/api/projects/{id}/study-plan'
      ? queued
      : open,
  )))
  client.POST.mockImplementation((url: string) => Promise.resolve(success(
    url === '/api/exercise-attempts'
      ? open
      : url.endsWith('/confirm')
        ? confirmed
        : graded,
  )))
})
afterEach(() => {
  cleanup?.()
  cleanup = undefined
  document.body.innerHTML = ''
})

describe('project review session', () => {
  it('submits opaque recognition IDs, shows only server feedback and confirms a manual Easy before refreshing progress', async () => {
    const app = await render()
    expect(app.wrapper.text()).not.toContain('Correct answer:')
    await answer()
    expect(client.POST).toHaveBeenLastCalledWith('/api/exercise-attempts/{attempt_id}/answer', {
      params: {
        path: { attempt_id: open.id },
      },
      body: {
        answer: 'opaque-bank',
        duration_ms: expect.any(Number),
      },
    })
    expect(app.wrapper.text()).toContain('Suggested rating: Good')
    expect(app.wrapper.text()).toContain('Answer time: 125 ms')
    expect(client.GET).toHaveBeenCalledTimes(1)
    await button('4. Easy').trigger('click')
    client.GET.mockResolvedValue(success(empty))
    await button('Confirm rating and continue').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenLastCalledWith('/api/exercise-attempts/{attempt_id}/confirm', {
      params: {
        path: { attempt_id: open.id },
      },
      body: { rating: 4 },
    })
    expect(app.wrapper.get('[data-testid="review-empty"]').text()).toContain('Review complete')
    expect(app.wrapper.text()).toContain('1 done')
    expect(app.wrapper.text()).toContain('5 new')
    expect(JSON.parse(sessionStorage.getItem(key())!)).toEqual({
      completed: [open.id],
    })
    cleanup?.()
    await render()
    expect(client.POST.mock.calls.filter(([url]) => url.endsWith('/confirm'))).toHaveLength(1)
  })

  it('renders generic typed prompts (including scenario) and keeps exact original whitespace and duration', async () => {
    client.POST.mockResolvedValueOnce(success({
      ...open,
      exercise: 'scenario',
      kind: 'recall',
      prompt: { text: 'He went to the ___.', input: 'text', choices: [] },
    }))
    const app = await render()
    await app.wrapper.get('input').setValue('  BANK  ')
    await app.wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(client.POST.mock.calls[1]![1].body).toEqual({
      answer: '  BANK  ',
      duration_ms: expect.any(Number),
    })
  })
  it.each(['en', 'zh-CN'] as const)('renders protected image recall, retries unavailable media and releases blobs in %s', async (locale) => {
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:review-image')
    const revoke = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
    let mediaCalls = 0
    client.GET.mockImplementation(async (url: string) => {
      if (url === '/api/media/{rid}') {
        mediaCalls++
        return mediaCalls === 1
          ? failure('media.not_found', null, 404)
          : success(new Blob(['image'], { type: 'image/png' }))
      }
      return success(queued)
    })
    client.POST.mockResolvedValueOnce(success({
      ...open,
      exercise: 'image2word',
      kind: 'recall',
      prompt: {
        text: '',
        input: 'text',
        media_id: 'media:opaque',
        media_attribution: 'Photo by Alice',
      },
    }))
    const app = await render(locale)
    expect(app.wrapper.findComponent({ name: 'AudioButton' }).exists()).toBe(false)
    expect(app.wrapper.text()).not.toContain('bank')
    expect(app.wrapper.get('[data-testid="review-image"]').text()).toContain(locale === 'en'
      ? 'This image is unavailable.'
      : '此图片暂不可用。')
    await button(locale === 'en'
      ? 'Retry'
      : '重试').trigger('click')
    await flushPromises()
    expect(app.wrapper.get('img').attributes('src')).toBe('blob:review-image')
    expect(app.wrapper.get('img').attributes('alt')).toBe(locale === 'en'
      ? 'Private vocabulary image'
      : '私人词汇图片')
    expect(app.wrapper.get('[data-testid="review-image-attribution"]').text()).toContain('Photo by Alice')
    expect(client.GET).toHaveBeenLastCalledWith('/api/media/{rid}', expect.objectContaining({
      params: {
        path: { rid: 'media:opaque' },
      },
      parseAs: 'blob',
      signal: expect.any(AbortSignal),
    }))
    await app.wrapper.get('img').trigger('error')
    expect(revoke).toHaveBeenCalledWith('blob:review-image')
    await button(locale === 'en'
      ? 'Retry'
      : '重试').trigger('click')
    await flushPromises()
    cleanup?.()
    cleanup = undefined
    expect(revoke).toHaveBeenCalledTimes(2)
    vi.restoreAllMocks()
  })

  it('uses server-owned hints and permits give-up without an answer', async () => {
    client.POST.mockImplementation((url: string) => Promise.resolve(success(
      url.endsWith('/hint')
        ? { ...open, hint_used: true, hint: 'Starts with b' }
        : url.endsWith('/giveup')
          ? {
              ...graded,
              feedback: { correct: false, answer: 'bank' },
              auto_rating: 1,
            }
          : open,
    )))
    const app = await render()
    await button('Hint').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('Hint: Starts with b')
    expect(button('Hint').attributes('disabled')).toBeDefined()
    await button('Give up').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenLastCalledWith('/api/exercise-attempts/{attempt_id}/giveup', {
      params: {
        path: { attempt_id: open.id },
      },
      body: {
        duration_ms: expect.any(Number),
      },
    })
    expect(app.wrapper.text()).toContain('Not quite')
    expect(app.wrapper.text()).toContain('Suggested rating: Again')
  })

  it('locks duplicates while an answer is in flight and retries the identical body after a transport failure', async () => {
    const app = await render()
    let reject!: (error: Error) => void
    client.POST.mockImplementationOnce(() => new Promise((_resolve, fail) => reject = fail))
    const shell = app.wrapper.getComponent(ExerciseShell)
    shell.vm.$emit('answered', { answer: 'opaque-bank', duration_ms: 1234 })
    shell.vm.$emit('answered', { answer: 'opaque-tree', duration_ms: 9999 })
    await flushPromises()
    expect(client.POST).toHaveBeenCalledTimes(2)
    reject(new Error('offline'))
    await flushPromises()
    const body = client.POST.mock.calls[1]![1].body
    expect(JSON.parse(sessionStorage.getItem(key())!).pending.body).toEqual(body)
    await app.wrapper.get('[data-testid="review-retry"]').trigger('click')
    await flushPromises()
    expect(client.POST.mock.calls[2]![1].body).toEqual(body)
    expect(app.wrapper.text()).toContain('Suggested rating')
  })

  it('retries an uncertain confirmation with the same rating, never advances on grading alone', async () => {
    const app = await render()
    await answer()
    client.POST.mockRejectedValueOnce(new Error('lost receipt'))
    await button('4. Easy').trigger('click')
    await button('Confirm rating and continue').trigger('click')
    await flushPromises()
    expect(app.wrapper.find('[data-testid="review-exercise"]').exists()).toBe(true)
    expect(client.GET).toHaveBeenCalledTimes(1)
    client.GET.mockResolvedValue(success(empty))
    await app.wrapper.get('[data-testid="review-retry"]').trigger('click')
    await flushPromises()
    const confirmations = client.POST.mock.calls.filter(([url]) => url.endsWith('/confirm'))
    expect(confirmations).toHaveLength(2)
    expect(confirmations[0]![1]).toEqual(confirmations[1]![1])
    expect(app.wrapper.text()).toContain('Review complete')
  })

  it('restores an uncertain answer after refresh without issuing or changing the attempt', async () => {
    sessionStorage.setItem(key(), JSON.stringify({
      completed: [],
      attemptId: open.id,
      pending: {
        action: 'answer',
        body: { answer: 'opaque-bank', duration_ms: 4321 },
      },
    }))
    const app = await render()
    expect(client.POST).not.toHaveBeenCalled()
    expect(app.wrapper.get('[data-testid="review-error"]').attributes('data-error')).toBe('recoverable')
    await app.wrapper.get('[data-testid="review-retry"]').trigger('click')
    await flushPromises()
    expect(client.POST.mock.calls[0]![1].body).toEqual({ answer: 'opaque-bank', duration_ms: 4321 })
  })

  it('reads an already confirmed receipt after refresh without posting another confirmation', async () => {
    sessionStorage.setItem(key(), JSON.stringify({
      completed: [],
      attemptId: open.id,
      pending: {
        action: 'confirm',
        body: { rating: 4 },
      },
    }))
    client.GET.mockImplementation((url: string) => Promise.resolve(success(url.includes('study-plan')
      ? empty
      : confirmed)))
    const app = await render()
    expect(client.POST).not.toHaveBeenCalled()
    expect(app.wrapper.text()).toContain('1 done')
    expect(app.wrapper.text()).toContain('Review complete')
  })

  it.each([
    ['exercise.no_usable', 409, 'unusable'],
    ['exercise.expired', 410, 'expired'],
    ['exercise.stale', 409, 'stale'],
    ['exercise.not_found', 404, 'unavailable'],
    ['http.503', 503, 'recoverable'],
  ])('shows %s distinctly and does not silently skip a card', async (code, status, state) => {
    client.POST.mockResolvedValueOnce(failure(code, null, status))
    const app = await render()
    expect(app.wrapper.get('[data-testid="review-error"]').attributes('data-error')).toBe(state)
    expect(client.GET).toHaveBeenCalledTimes(1)
    expect(client.POST).toHaveBeenCalledTimes(1)
    expect(app.wrapper.text()).not.toContain('NEVER DISPLAY RAW')
  })

  it('requires an explicit fresh attempt after a stale answer response', async () => {
    const app = await render()
    client.POST.mockResolvedValueOnce(failure('exercise.stale', null, 409))
    await answer()
    expect(app.wrapper.get('[data-testid="review-error"]').attributes('data-error')).toBe('stale')
    await app.wrapper.get('[data-testid="review-restart"]').trigger('click')
    await flushPromises()
    expect(app.wrapper.get('[data-testid="review-exercise"]').attributes('data-status')).toBe('open')
    expect(JSON.parse(sessionStorage.getItem(key())!).pending).toBeUndefined()
    expect(client.POST.mock.calls.filter(([url]) => url === '/api/exercise-attempts')).toHaveLength(2)
  })

  it('keeps answering available when the server has no hint', async () => {
    const app = await render()
    client.POST.mockResolvedValueOnce(failure('exercise.hint_unavailable', null, 409))
    await button('Hint').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('No hint is available')
    expect(button('Give up').attributes('disabled')).toBeUndefined()
    await answer()
    expect(app.wrapper.text()).toContain('Suggested rating')
  })

  it('distinguishes loading, initial empty and failed queue requests', async () => {
    let finish!: (value: ReturnType<typeof success>) => void
    client.GET.mockImplementationOnce(() => new Promise(resolve => finish = resolve))
    const app = await render()
    expect(app.wrapper.find('[data-testid="review-loading"]').exists()).toBe(true)
    finish(success(empty))
    await flushPromises()
    expect(app.wrapper.text()).toContain('Nothing to study now')
    expect(client.POST).not.toHaveBeenCalled()
    client.GET.mockRejectedValueOnce(new Error('network'))
    await button('Refresh').trigger('click')
    await flushPromises()
    expect(app.wrapper.get('[data-testid="review-error"]').attributes('data-error')).toBe('recoverable')
  })

  it('shows missing protected audio explicitly and still allows give-up', async () => {
    client.POST.mockResolvedValueOnce(success({
      ...open,
      kind: 'recall',
      prompt: {
        text: '',
        input: 'text',
        choices: [],
        media_id: 'media:protected',
      },
    }))
    const app = await render()
    client.GET.mockResolvedValueOnce(failure('media.not_found', null, 404))
    await app.wrapper.get('button[aria-label="Play pronunciation"]').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/media/{rid}', expect.objectContaining({
      parseAs: 'blob',
      params: {
        path: { rid: 'media:protected' },
      },
    }))
    expect(app.wrapper.get('[data-testid="review-audio-error"]').text()).toContain('Audio unavailable')
    expect(button('Give up').attributes('disabled')).toBeUndefined()
  })

  it('confirms navigation, retains the attempt, and scopes persistence by owner and project', async () => {
    const app = await render()
    expect(JSON.parse(sessionStorage.getItem(key())!).attemptId).toBe(open.id)
    await app.wrapper.get('[data-testid="review-exit"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Leave this review?')
    await button('Keep studying').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('project-review')
    auth.user.id = 'user:other'
    await flushPromises()
    expect(client.POST.mock.calls.filter(([url]) => url === '/api/exercise-attempts')).toHaveLength(2)
    expect(sessionStorage.getItem(reviewSessionKey('user:learner', project.id))).not.toBeNull()
    expect(sessionStorage.getItem(reviewSessionKey('user:other', project.id))).not.toBeNull()
  })

  it('blocks submission when durable request storage fails', async () => {
    const app = await render()
    const storage = vi.spyOn(sessionStorage, 'setItem').mockImplementation(() => {
      throw new Error('denied')
    })
    await answer()
    expect(client.POST).toHaveBeenCalledTimes(1)
    expect(app.wrapper.get('[data-testid="review-error"]').attributes('data-error')).toBe('storage')
    storage.mockRestore()
    await app.wrapper.get('[data-testid="review-retry"]').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledTimes(2)
  })

  it('supports Chinese chrome without translating learning content', async () => {
    const app = await render('zh-CN')
    expect(app.wrapper.text()).toContain('项目复习')
    expect(app.wrapper.text()).toContain('A financial institution')
    expect(app.wrapper.text()).not.toContain('session.')
  })
})
