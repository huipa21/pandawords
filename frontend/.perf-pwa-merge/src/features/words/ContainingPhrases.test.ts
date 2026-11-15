import type { components } from '@/api/schema'
import { DOMWrapper, flushPromises } from '@vue/test-utils'
import { NSelect } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AddWordDialog from '@/features/projects/AddWordDialog.vue'
import { base, cleanup, fail, ok, setup } from './testHarness'

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
const phrase: components['schemas']['Candidate'] = {
  lemma: {
    id: ['en', 'heavy rain'],
    text: 'heavy rain',
    lang: 'en',
    kind: 'phrase',
    freq_zipf: null,
    cefr: null,
    source: 'test',
  },
  matched_by: ['exact'],
  lexemes: [
    {
      lexeme: {
        id: ['en', 'heavy rain', 'noun', 1],
        lemma_id: ['en', 'heavy rain'],
        pos: 'noun',
        etymology_no: 1,
        etymology_text: null,
        source: 'test',
      },
      pronunciations: [],
      glosses: [],
      senses: ['Intense rainfall', 'Another meaning'].map((definition, rank) => ({
        id: [
          'en',
          'heavy rain',
          'noun',
          1,
          `s${rank}`,
        ],
        lexeme_id: ['en', 'heavy rain', 'noun', 1],
        definition,
        glosses: [],
        gloss_zh: null,
        tags: [],
        register: [],
        domain: [],
        examples: [],
        rank,
        common: rank === 0,
        source: 'test',
        source_id: null,
        lexname: null,
      })),
    },
  ],
}
const item: components['schemas']['ContainingPhraseRead'] = {
  entry: {
    lemma: {
      id: 'lemma:phrase',
      table: 'lemma',
      owner: null,
      fields: { text: 'heavy rain', kind: 'phrase' },
    },
    lexemes: [],
  },
  candidate: phrase,
}
const page = {
  items: [item],
  sources: [],
  offset: 0,
  limit: 20,
  has_more: false,
}
beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockImplementation(async (path: string) => {
    if (path.endsWith('/phrases'))
      return ok(page)
    if (path.endsWith('/entry'))
      return ok(base)
    if (path.endsWith('/override'))
      return fail(404)
    if (path === '/api/projects') {
      return ok({
        items: [
          { id: 'project:one', name: 'My project' },
        ],
        total: 1,
      })
    }
    return ok([])
  })
})
afterEach(() => {
  cleanup()
  document.body.innerHTML = ''
})

describe('phrase composition and normal project add', () => {
  it('navigates to the precise phrase identity, never a component sense', async () => {
    const { wrapper, router } = await setup()
    expect(wrapper.get('[data-testid="containing-phrases"]').text()).toContain('not evidence')
    await wrapper.get('[data-testid="phrase-detail"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.params.lemmaId).toBe('lemma:phrase')
  })

  it('loads projects and searches the phrase in the existing selected-sense dialog', async () => {
    client.POST.mockResolvedValue(ok({
      normalized: 'heavy rain',
      candidates: [phrase],
      sources: [],
    }))
    const { wrapper } = await setup()
    await wrapper.get('[data-testid="phrase-add"]').trigger('click')
    await flushPromises()
    const select = wrapper.findComponent(NSelect)
    select.vm.$emit('update:value', 'project:one')
    await flushPromises()
    await wrapper.get('[data-testid="phrase-choose-senses"]').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/dictionary/candidates', {
      body: { text: 'heavy rain' },
      signal: expect.any(AbortSignal),
    })
    const rare = document.body.querySelector('[role="checkbox"][aria-label="Another meaning"]')
    expect(rare?.getAttribute('aria-checked')).toBe('false')
    client.POST.mockResolvedValue(ok({
      project_id: 'project:one',
      lemma_id: 'lemma:phrase',
      lexeme_ids: [],
      selected_sense_ids: ['sense:phrase'],
      membership_ids: [],
      jobs: [],
    }))
    await new DOMWrapper(document.body.querySelector('[data-testid="add-word-submit"]')!).trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenLastCalledWith('/api/projects/{id}/dictionary', {
      params: {
        path: { id: 'project:one' },
      },
      body: {
        lemma_key: phrase.lemma.id,
        selected_senses: [phrase.lexemes[0]!.senses[0]!.id],
      },
      signal: expect.any(AbortSignal),
    })
    expect(wrapper.findComponent(AddWordDialog).emitted('added')).toHaveLength(1)
  })

  it.each(['en', 'zh-CN'] as const)('shows localized loading, empty, failure and retry in %s', async (locale) => {
    let resolve!: (value: unknown) => void
    client.GET.mockImplementation(async (path: string) => {
      if (path.endsWith('/phrases'))
        return new Promise(done => resolve = done)
      if (path.endsWith('/entry'))
        return ok(base)
      if (path.endsWith('/override'))
        return fail(404)
      return ok([])
    })
    const { wrapper } = await setup(locale)
    const panel = wrapper.get('[data-testid="containing-phrases"]')
    expect(panel.find('[role="status"]').exists()).toBe(true)
    resolve(fail())
    await flushPromises()
    expect(panel.get('[role="alert"]').text()).toContain(locale === 'en'
      ? 'Could not load phrases'
      : '无法加载短语')
    client.GET.mockResolvedValueOnce(ok({ ...page, items: [] }))
    await new DOMWrapper(panel.get('[role="alert"] button').element).trigger('click')
    await flushPromises()
    expect(panel.text()).toContain(locale === 'en'
      ? 'No materialized phrases'
      : '尚无已入库短语')
  })

  it('keeps phrase search no-match and transport errors inside the ordinary add dialog', async () => {
    const { wrapper } = await setup()
    await wrapper.get('[data-testid="phrase-add"]').trigger('click')
    await flushPromises()
    wrapper.findComponent(NSelect).vm.$emit('update:value', 'project:one')
    await flushPromises()
    client.POST.mockResolvedValueOnce(ok({ normalized: 'heavy rain', candidates: [], sources: [] }))
    await wrapper.get('[data-testid="phrase-choose-senses"]').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('[data-testid="add-word-submit"]')).toBeNull()
    expect(document.body.textContent).toContain('No matches')
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await new DOMWrapper(document.body.querySelector('[data-testid="add-word-search"]')!).trigger('click')
    await flushPromises()
    expect(document.body.querySelector('[data-testid="add-word-error"]')).not.toBeNull()
    expect(client.POST).toHaveBeenLastCalledWith('/api/dictionary/candidates', {
      body: { text: 'heavy rain' },
      signal: expect.any(AbortSignal),
    })
  })
})
