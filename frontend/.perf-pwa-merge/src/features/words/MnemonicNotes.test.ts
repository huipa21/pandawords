import type { components } from '@/api/schema'
import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import LemmaNotes from './LemmaNotes.vue'
import { base, fail, ok } from './testHarness'
import { useWordDrafts } from './useWordDrafts'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', async (original) => {
  const module = await original<typeof import('@/api/client')>()
  return { ...module, api: client }
})
const user: components['schemas']['UserRead'] = {
  id: 'alice',
  username: 'alice',
  role: 'user',
  disabled: false,
  must_change_password: false,
  source_lang: 'zh',
  target_lang: 'en',
  prefs: {
    theme: 'system',
    locale: 'en',
    accent: 'US',
    desired_retention: 0.9,
    review_images_enabled: true,
    review_audio_enabled: true,
  },
}
let dispose: (() => void) | undefined
let saved: components['schemas']['NoteRead'][]

async function setup(locale: 'en' | 'zh-CN' = 'en') {
  const pinia = createPinia()
  const auth = useAuthStore(pinia)
  auth.user = { ...user }
  const target = ref(base.lemma)
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(defineComponent({
    setup: () => () => h(NConfigProvider, null, {
      default: () => h(NMessageProvider, null, {
        default: () => h(LemmaNotes, { target: target.value }),
      }),
    }),
  }), {
    attachTo: document.body,
    global: {
      plugins: [pinia, i18n],
    },
  })
  dispose = () => wrapper.unmount()
  await flushPromises()
  return {
    wrapper,
    auth,
    target,
    drafts: useWordDrafts(pinia),
  }
}

beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  saved = []
  client.GET.mockImplementation(async (path: string) => path === '/api/notes'
    ? ok(saved)
    : ok({ status: 'pending', job_id: 'job' }))
  client.POST.mockImplementation(async (path: string, options: { body: components['schemas']['NoteCreate'] }) => {
    if (path === '/api/notes/suggestions')
      return ok({ status: 'ready', text: 'Imagine racing shoes.' })
    const note = { ...options.body, id: `note:${saved.length}`, kind: options.body.kind ?? 'note' }
    saved.push(note)
    return ok(note)
  })
  client.PATCH.mockImplementation(async (_path: string, options: { body: { text: string }, params: { path: { id: string } } }) => {
    const note = saved.find(item => item.id === options.params.path.id)!
    note.text = options.body.text
    return ok(note)
  })
  client.DELETE.mockResolvedValue({
    response: new Response(null, { status: 204 }),
  })
})
afterEach(() => {
  dispose?.()
  vi.useRealTimers()
  document.body.innerHTML = ''
})

describe('mnemonic notes', () => {
  it.each(['en', 'zh-CN'] as const)('keeps generation separate, confirms replacement, edits and explicitly saves only mnemonics (%s)', async (locale) => {
    saved = [
      {
        target_table: 'lemma',
        target_id: base.lemma.id,
        id: 'ordinary',
        kind: 'note',
        text: 'Ordinary note',
      },
    ]
    const { wrapper } = await setup(locale)
    await wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    await wrapper.get('textarea').setValue('My unsaved mnemonic')
    await wrapper.get('[data-testid="mnemonic-generate"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="mnemonic-result"]').text()).toBe('Imagine racing shoes.')
    expect(wrapper.get('textarea').element.value).toBe('My unsaved mnemonic')
    expect(saved).toHaveLength(1)
    await wrapper.get('[data-testid="mnemonic-accept"]').trigger('click')
    const confirmation = wrapper.findAllComponents(ConfirmAction).find(item => item.props('show'))!
    expect(confirmation.exists()).toBe(true)
    confirmation.vm.$emit('cancel')
    expect(wrapper.get('textarea').element.value).toBe('My unsaved mnemonic')
    await wrapper.get('[data-testid="mnemonic-accept"]').trigger('click')
    confirmation.vm.$emit('confirm')
    await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('Imagine racing shoes.')
    expect(saved).toHaveLength(1)
    await wrapper.get('textarea').setValue('My edited suggestion')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(saved).toHaveLength(2)
    expect(saved[0]!.text).toBe('Ordinary note')
    expect(saved[1]).toMatchObject({ kind: 'mnemonic', text: 'My edited suggestion', target_id: base.lemma.id })
    expect(client.POST).toHaveBeenCalledWith('/api/notes/suggestions', {
      body: { target_table: 'lemma', target_id: base.lemma.id },
    })
    await wrapper.findAll('[data-testid="word-note-edit"]')[1]!.trigger('click')
    await wrapper.get('textarea').setValue('Hand-edited mnemonic')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH).toHaveBeenCalledWith('/api/notes/{id}', {
      params: {
        path: { id: 'note:1' },
      },
      body: { text: 'Hand-edited mnemonic' },
    })
    await wrapper.findAll('[data-testid="word-note-delete"]')[1]!.trigger('click')
    wrapper.findAllComponents(ConfirmAction).find(item => item.props('show'))!.vm.$emit('confirm')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="word-note"]')).toHaveLength(1)
    expect(wrapper.text()).toContain('Ordinary note')
  })

  it('retains both kinds, navigation/refresh and failed saves; isolates signed-in owners', async () => {
    const first = await setup()
    await first.wrapper.get('textarea').setValue('Ordinary draft')
    await first.wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    await first.wrapper.get('textarea').setValue('Mnemonic draft')
    client.POST.mockResolvedValueOnce(fail())
    await first.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(first.wrapper.get('textarea').element.value).toBe('Mnemonic draft')
    first.target.value = base.lexemes[0]!.lexeme
    await flushPromises()
    expect(first.wrapper.get('textarea').element.value).toBe('')
    await first.wrapper.get('textarea').setValue('Lexeme mnemonic')
    first.target.value = base.lemma
    await flushPromises()
    expect(first.wrapper.get('textarea').element.value).toBe('Mnemonic draft')
    first.auth.user = { ...user, id: 'bob' }
    await flushPromises()
    expect(first.wrapper.get('textarea').element.value).toBe('')
    first.auth.user = { ...user }
    await flushPromises()
    expect(first.wrapper.get('textarea').element.value).toBe('Mnemonic draft')
    dispose?.()
    const second = await setup()
    expect(second.wrapper.get('textarea').element.value).toBe('Ordinary draft')
    await second.wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    expect(second.wrapper.get('textarea').element.value).toBe('Mnemonic draft')
  })

  it.each([
    'disabled',
    'budget_exhausted',
    'provider_error',
    'timeout',
    'stale_content',
  ])('allows manual editing when %s and offers explicit retry', async (reason) => {
    client.POST.mockResolvedValueOnce(ok({ status: 'unavailable', reason }))
    const { wrapper } = await setup()
    await wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    await wrapper.get('textarea').setValue('Offline draft')
    await wrapper.get('[data-testid="mnemonic-generate"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).not.toContain('mnemonics.')
    expect(wrapper.get('[data-testid="mnemonic-generate"]').text()).toContain('Retry')
    expect(wrapper.get('textarea').element.value).toBe('Offline draft')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(saved[0]).toMatchObject({ kind: 'mnemonic', text: 'Offline draft' })
  })

  it.each(['target', 'user', 'cancel'] as const)('ignores late generation after %s changes and never saves it', async (change) => {
    let resolve!: (value: unknown) => void
    client.POST.mockReturnValueOnce(new Promise(done => resolve = done))
    const { wrapper, target, auth } = await setup()
    await wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    await wrapper.get('textarea').setValue('Keep me')
    await wrapper.get('[data-testid="mnemonic-generate"]').trigger('click')
    if (change === 'target')
      target.value = base.lexemes[0]!.senses[0]!
    else if (change === 'user')
      auth.user = { ...user, id: 'bob' }
    else
      await wrapper.get('[data-testid="mnemonic-reject"]').trigger('click')
    await flushPromises()
    resolve(ok({ status: 'ready', text: 'Late private suggestion' }))
    await flushPromises()
    expect(wrapper.find('[data-testid="mnemonic-result"]').exists()).toBe(false)
    expect(saved).toEqual([])
    expect(wrapper.get('textarea').element.value).toBe(change === 'cancel'
      ? 'Keep me'
      : '')
  })

  it('polls explicit jobs, rejects a suggestion and stops polling after cancellation', async () => {
    vi.useFakeTimers()
    client.POST.mockResolvedValueOnce(ok({ status: 'pending', job_id: 'job' }))
    client.GET.mockImplementation(async (path: string) => path === '/api/notes'
      ? ok([])
      : ok({ status: 'ready', text: 'Worker result' }))
    const { wrapper } = await setup()
    await wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    await wrapper.get('[data-testid="mnemonic-generate"]').trigger('click')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    expect(wrapper.get('[data-testid="mnemonic-result"]').text()).toBe('Worker result')
    await wrapper.get('[data-testid="mnemonic-reject"]').trigger('click')
    expect(wrapper.get('textarea').element.value).toBe('')
    client.POST.mockResolvedValueOnce(ok({ status: 'pending', job_id: 'second' }))
    await wrapper.get('[data-testid="mnemonic-generate"]').trigger('click')
    await flushPromises()
    const calls = client.GET.mock.calls.length
    await wrapper.get('[data-testid="mnemonic-reject"]').trigger('click')
    await vi.advanceTimersByTimeAsync(5000)
    expect(client.GET).toHaveBeenCalledTimes(calls)
    expect(saved).toEqual([])
  })

  it.each(['target', 'user'] as const)('does not apply an old save response after a %s switch', async (change) => {
    let resolve!: (value: unknown) => void
    const { wrapper, target, auth } = await setup()
    await wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    await wrapper.get('textarea').setValue('Old draft')
    client.POST.mockReturnValueOnce(new Promise(done => resolve = done))
    await wrapper.get('form').trigger('submit')
    if (change === 'target')
      target.value = base.lexemes[0]!.senses[0]!
    else
      auth.user = { ...user, id: 'bob' }
    await flushPromises()
    await wrapper.get('textarea').setValue('New draft')
    resolve(ok({
      id: 'old',
      kind: 'mnemonic',
      text: 'Old draft',
      target_table: 'lemma',
      target_id: base.lemma.id,
    }))
    await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('New draft')
    expect(wrapper.findAll('[data-testid="word-note"]')).toHaveLength(0)
  })

  it('keeps manual drafts editable when all requests or browser storage fail', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked')
    })
    client.GET.mockRejectedValue(new Error('offline'))
    const { wrapper } = await setup()
    await wrapper.get('[data-testid="word-kind-mnemonic"]').trigger('click')
    expect(wrapper.get('textarea').attributes('disabled')).toBeUndefined()
    await wrapper.get('textarea').setValue('Still editing offline')
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('textarea').element.value).toBe('Still editing offline')
    vi.restoreAllMocks()
  })
})
