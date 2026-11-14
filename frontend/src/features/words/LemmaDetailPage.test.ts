import type { components } from '@/api/schema'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { base, button, cleanup, fail, ok, setup } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  PATCH: vi.fn(),
  POST: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', async (original) => {
  const module = await original<typeof import('@/api/client')>()
  return { ...module, api: client }
})
let entry: components['schemas']['DictionaryEntryRead']
let own: components['schemas']['OverrideRead'] | undefined
let notes: components['schemas']['NoteRead'][]
beforeEach(() => {
  vi.resetAllMocks()
  entry = structuredClone(base)
  own = undefined
  notes = []
  client.GET.mockImplementation(async (path: string, options: { params: { path?: { id?: string }, query?: { target_id: string } } }) => {
    if (path.endsWith('/entry'))
      return ok(structuredClone(entry))
    if (path.endsWith('/override')) {
      return own?.target_id === options.params.path?.id
        ? ok(own)
        : fail(404)
    }
    return ok(notes.filter(note => note.target_id === options.params.query?.target_id))
  })
  client.DELETE.mockResolvedValue({
    response: new Response(null, { status: 204 }),
  })
})
afterEach(() => {
  cleanup?.()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('lemma detail', () => {
  it('opens the sense tag panel with only the selected opaque sense target', async () => {
    const { wrapper } = await setup()
    expect(wrapper.find('[data-testid="tag-assignments"]').exists()).toBe(false)
    await wrapper.get('[data-testid="word-sense-tags"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="tag-assignments"]').exists()).toBe(true)
    expect(client.GET).toHaveBeenCalledWith('/api/tags/assignments', {
      params: {
        query: { target_table: 'sense', target_id: 'sense:opaque' },
      },
    })
    await wrapper.get('[data-testid="word-sense-tags"]').trigger('click')
    expect(wrapper.find('[data-testid="tag-assignments"]').exists()).toBe(false)
  })

  it('shows first-load skeletons and ignores late entry responses after changing lemmas', async () => {
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise(done => resolve = done))
    const { wrapper, router } = await setup('en', false)
    expect(wrapper.get('[role="status"]').attributes('aria-label')).toBe('Loading')
    entry.lemma = {
      ...entry.lemma,
      id: 'lemma:other',
      fields: { text: 'other' },
    }
    await router.push({
      name: 'word',
      params: { lemmaId: entry.lemma.id },
    })
    await flushPromises()
    resolve(ok(base))
    await flushPromises()
    expect(wrapper.get('[data-testid="word-detail"]').text()).toContain('other')
    expect(wrapper.get('[data-testid="word-detail"]').text()).not.toContain('run')
  })

  it('edits effective own sense fields, preserves other language glosses, refreshes and confirms whole-overlay reset', async () => {
    const { wrapper, router } = await setup()
    expect(wrapper.text()).toContain('Move quickly')
    client.PATCH.mockImplementation(async (_path: string, options: { body: components['schemas']['OverrideUpdate'] }) => {
      own = {
        target_id: 'sense:opaque',
        target_table: 'sense',
        fields: options.body.fields,
        updated_at: '2026-11-14T00:00:00Z',
      }
      entry.lexemes[0]!.senses[0]!.fields.definition = options.body.fields.definition
      entry.lexemes[0]!.senses[0]!.fields.gloss = { fr: 'courir', ...options.body.fields.gloss }
      return ok(own)
    })
    await wrapper.get('[data-testid="word-sense-edit"]').trigger('click')
    await wrapper.get('#word-override-definition').setValue('My running meaning')
    await wrapper.get('#word-override-gloss').setValue('我的释义')
    await wrapper.get('[data-testid="word-override-save"]').trigger('click')
    await flushPromises()
    expect(client.PATCH).toHaveBeenCalledWith('/api/dictionary/{table}/{id}/override', {
      params: {
        path: { table: 'sense', id: 'sense:opaque' },
      },
      body: {
        fields: {
          definition: 'My running meaning',
          gloss: { zh: '我的释义' },
        },
      },
    })
    expect(wrapper.get('[data-testid="word-sense"]').text()).toContain('Customized')
    await wrapper.get('[data-testid="word-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('My running meaning')
    await router.push({
      name: 'project',
      params: { id: 'project:one' },
    })
    await router.push({
      name: 'word',
      params: { lemmaId: base.lemma.id },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('My running meaning')
    expect(entry.lexemes[0]!.senses[0]!.fields.gloss).toEqual({ zh: '我的释义', fr: 'courir' })
    await wrapper.get('[data-testid="word-sense-reset"]').trigger('click')
    expect(client.DELETE).not.toHaveBeenCalled()
    client.DELETE.mockResolvedValueOnce(fail())
    client.DELETE.mockImplementation(async () => {
      own = undefined
      entry = structuredClone(base)
      return {
        response: new Response(null, { status: 204 }),
      }
    })
    wrapper.findAllComponents(ConfirmAction).find(component => component.props('show'))!.vm.$emit('confirm')
    await flushPromises()
    expect(wrapper.text()).toContain('My running meaning')
    expect(wrapper.findAllComponents(ConfirmAction).some(component => component.props('show'))).toBe(true)
    wrapper.findAllComponents(ConfirmAction).find(component => component.props('show'))!.vm.$emit('confirm')
    await flushPromises()
    expect(client.DELETE).toHaveBeenCalledWith('/api/dictionary/{table}/{id}/override', {
      params: {
        path: { table: 'sense', id: 'sense:opaque' },
      },
    })
    expect(wrapper.text()).toContain('Move quickly')
    expect(wrapper.find('[data-testid="word-sense-reset"]').exists()).toBe(false)
  })

  it('keeps unsaved drafts across refresh and project navigation, and retains draft on failed override writes', async () => {
    const { wrapper, router } = await setup()
    await wrapper.get('[data-testid="word-note-editor"] textarea').setValue('Unsaved note')
    await wrapper.get('[data-testid="word-sense-edit"]').trigger('click')
    await wrapper.get('#word-override-definition').setValue('Unsaved draft')
    await wrapper.get('[data-testid="word-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.get<HTMLInputElement>('#word-override-definition').element.value).toBe('Unsaved draft')
    await router.push({
      name: 'project',
      params: { id: 'project:one' },
    })
    await router.push({
      name: 'word',
      params: { lemmaId: base.lemma.id },
    })
    await flushPromises()
    expect(wrapper.get<HTMLTextAreaElement>('[data-testid="word-note-editor"] textarea').element.value).toBe('Unsaved note')
    await wrapper.get('[data-testid="word-sense-edit"]').trigger('click')
    expect(wrapper.get<HTMLInputElement>('#word-override-definition').element.value).toBe('Unsaved draft')
    client.PATCH.mockResolvedValueOnce(fail(422, 'fields.definition'))
    await wrapper.get('[data-testid="word-override-save"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="word-override-editor"]').text()).toContain('The request failed. Please try again.')
    expect(wrapper.get<HTMLInputElement>('#word-override-definition').element.value).toBe('Unsaved draft')
    expect(document.body.textContent).not.toContain('SECRET SERVER TEXT')
  })

  it('adds, edits and confirms deleting own target notes; failed requests keep edits', async () => {
    const { wrapper } = await setup()
    expect(wrapper.text()).toContain('No personal notes yet.')
    const note: components['schemas']['NoteRead'] = {
      id: 'note:opaque',
      target_id: base.lemma.id,
      target_table: 'lemma',
      kind: 'note',
      text: 'Memory aid',
    }
    client.POST.mockResolvedValueOnce(ok(note))
    await wrapper.get('[data-testid="word-note-editor"] textarea').setValue(note.text)
    await button('Save').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/notes', {
      body: {
        target_table: 'lemma',
        target_id: base.lemma.id,
        kind: 'note',
        text: note.text,
      },
    })
    await wrapper.get('[data-testid="word-note-edit"]').trigger('click')
    await wrapper.get('[data-testid="word-note-editor"] textarea').setValue('Updated memory')
    client.PATCH.mockRejectedValueOnce(new Error('offline'))
    await button('Save').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Cannot reach the server.')
    expect(wrapper.get<HTMLTextAreaElement>('[data-testid="word-note-editor"] textarea').element.value).toBe('Updated memory')
    client.PATCH.mockResolvedValueOnce(ok({ ...note, text: 'Updated memory' }))
    await button('Save').trigger('click')
    await flushPromises()
    expect(client.PATCH).toHaveBeenLastCalledWith('/api/notes/{id}', {
      params: {
        path: { id: note.id },
      },
      body: { text: 'Updated memory' },
    })
    expect(wrapper.get('[data-testid="word-note"]').text()).toContain('Updated memory')
    await wrapper.get('[data-testid="word-note-delete"]').trigger('click')
    expect(client.DELETE).not.toHaveBeenCalled()
    client.DELETE.mockResolvedValueOnce(fail())
    wrapper.findAllComponents(ConfirmAction).find(component => component.props('show'))!.vm.$emit('confirm')
    await flushPromises()
    expect(wrapper.find('[data-testid="word-note"]').exists()).toBe(true)
    wrapper.findAllComponents(ConfirmAction).find(component => component.props('show'))!.vm.$emit('confirm')
    await flushPromises()
    expect(wrapper.find('[data-testid="word-note"]').exists()).toBe(false)
  })

  it('shows missing audio without fetching a protected URL and guards malformed JSON fields', async () => {
    entry.lexemes[0]!.senses[0]!.fields = {
      definition: { bad: true },
      gloss: ['bad'],
      examples: [null, 'An example'],
    }
    const { wrapper } = await setup()
    expect(wrapper.text()).toContain('No pronunciation audio is available.')
    await wrapper.get('[data-testid="word-pronunciation"] button').trigger('click')
    await flushPromises()
    expect(client.GET.mock.calls.some(([path]) => path === '/api/media/{rid}')).toBe(false)
    expect(wrapper.text()).not.toContain('[object Object]')
  })

  it('toggles authenticated audio and exposes playback state on the pronunciation button', async () => {
    const pause = vi.fn()
    vi.stubGlobal('Audio', class {
      src = ''
      pause = pause
      play = vi.fn().mockResolvedValue(undefined)
    })
    vi.stubGlobal('URL', class extends URL {
      static createObjectURL = vi.fn(() => 'blob:pronunciation')
      static revokeObjectURL = vi.fn()
    })
    entry.lexemes[0]!.lexeme.fields.pron = [
      { accent: 'US', ipa: 'rʌn', audio: 'media:one' },
    ]
    const get = client.GET.getMockImplementation()!
    client.GET.mockImplementation((path: string, options: { params: { path?: { id?: string }, query?: { target_id: string } } }) => path === '/api/media/{rid}'
      ? Promise.resolve(ok(new Blob(['audio'])))
      : get(path, options))
    const { wrapper } = await setup()
    const audio = wrapper.get('[data-testid="word-pronunciation"] button')
    expect(audio.attributes('aria-pressed')).toBe('false')
    await audio.trigger('click')
    await flushPromises()
    expect(audio.attributes('aria-pressed')).toBe('true')
    await audio.trigger('click')
    expect(audio.attributes('aria-pressed')).toBe('false')
    expect(pause).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:pronunciation')
  })

  it('handles first-load, missing target, note and refresh failures without discarding confirmed content', async () => {
    client.GET.mockResolvedValueOnce(fail(404))
    const { wrapper } = await setup('zh-CN')
    expect(wrapper.text()).toContain('该单词不可用。')
    await button('重试').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Move quickly')
    client.GET.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="word-refresh"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Move quickly')
    expect(document.body.textContent).not.toContain('SECRET SERVER TEXT')
    client.GET.mockResolvedValueOnce(fail())
    await wrapper.get('[data-testid="word-notes"] button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="word-notes"]').text()).toContain('请求失败，请重试。')
  })
})
