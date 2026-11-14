import type { Reading } from './readingText'
import { flushPromises, mount } from '@vue/test-utils'
import { NInput, NSelect } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createAppI18n } from '@/i18n'
import ReadingLookup from './ReadingLookup.vue'
import ReadingPage from './ReadingPage.vue'
import { occurrenceState, readingSegments } from './readingText'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
function content(id: string, text: string, kind: 'sentence' | 'passage' = 'sentence') {
  return {
    id,
    text,
    kind,
    lang: 'en',
    source: 'Original source',
    title: '',
    translation: {},
  }
}
function fixture(): Reading {
  return {
    passage: {
      ...content('passage', '🙂 cat.\n bank unknown!', 'passage'),
      title: 'Original title',
    },
    sentences: [
      {
        sentence: content('second', 'bank unknown!'),
        order: 1,
        span: [8, 21],
        occurrences: [
          {
            text: 'bank',
            span: [0, 4],
            candidates: [],
            status: 'resolved',
            sense_id: 'other',
          },
          {
            text: 'unknown',
            span: [5, 12],
            candidates: [],
            status: 'unmatched',
          },
        ],
      },
      {
        sentence: content('first', '🙂 cat.\n '),
        order: 0,
        span: [0, 8],
        occurrences: [
          {
            text: 'cat',
            span: [2, 5],
            candidates: [],
            status: 'resolved',
            sense_id: 'visible',
          },
        ],
      },
    ],
    assistance: 'not_requested',
    project_senses: [
      {
        id: 'visible',
        table: 'sense',
        owner: null,
        fields: {
          definition: 'Effective cat',
          gloss: { zh: '我的猫' },
        },
      },
    ],
  }
}
const candidate = {
  lemma: {
    id: ['en', 'bank'],
    text: 'bank',
  },
  lexemes: [
    {
      lexeme: { pos: 'noun' },
      senses: [
        {
          id: ['en', 'bank', 'noun', 1, 'one'],
          definition: 'Financial institution',
        },
        {
          id: ['en', 'bank', 'noun', 1, 'two'],
          definition: 'River side',
        },
      ],
    },
  ],
}
function ok(data: unknown) {
  return {
    data,
    response: { status: 200 },
  }
}
function fail(status = 500) {
  return {
    error: {},
    response: { status },
  }
}
let wrapper: ReturnType<typeof mount>
async function setup(path = '/reading/passage', locale: 'en' | 'zh-CN' = 'en') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reading/:passageId?', name: 'reading', component: ReadingPage },
    ],
  })
  await router.push(path)
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  wrapper = mount(ReadingPage, {
    global: {
      plugins: [router, i18n],
    },
  })
  await flushPromises()
  return wrapper
}
function button(text: string) {
  const node = wrapper.findAll('button').find(item => item.text() === text)
  if (!node)
    throw new Error(`Missing button: ${text}`)
  return node
}
beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockImplementation(async (path: string) => {
    if (path === '/api/projects') {
      return ok({
        items: [
          { id: 'project', name: 'My project' },
        ],
        total: 1,
      })
    }
    if (path === '/api/content/{kind}')
      return ok([])
    return ok(fixture())
  })
  client.POST.mockImplementation(async (path: string) => {
    if (path === '/api/dictionary/candidates') {
      return ok({
        candidates: [candidate],
      })
    }
    return ok({
      selected_sense_ids: ['chosen'],
    })
  })
  client.PUT.mockResolvedValue(ok({ occurrences: [] }))
})
afterEach(() => wrapper?.unmount())

describe('reading text and project context', () => {
  it('preserves original text, order, gaps and Unicode offsets with three distinct states', () => {
    const data = fixture()
    const segments = readingSegments(data)
    expect(segments.map(item => item.text).join('')).toBe(data.passage.text)
    expect(segments.filter(item => item.occurrence).map(item => item.text)).toEqual(['cat', 'bank', 'unknown'])
    expect(segments.filter(item => item.occurrence).map(item => occurrenceState(data, item.occurrence!))).toEqual(['selected', 'outside', 'unlinked'])
    data.project_senses = []
    expect(occurrenceState(data, segments[1]!.occurrence!)).toBe('outside')
    data.sentences = []
    expect(readingSegments(data).map(item => item.text).join('')).toBe(data.passage.text)
  })
  it('renders only server-selected highlights and effective definitions', async () => {
    await setup()
    expect(wrapper.find('article').text()).toBe('🙂 cat.\n bank unknown!')
    expect(wrapper.find('[data-state="selected"]').text()).toBe('cat')
    expect(wrapper.find('[data-state="outside"]').text()).toBe('bank')
    await wrapper.find('[data-state="selected"]').trigger('click')
    expect(wrapper.text()).toContain('Effective cat')
    expect(wrapper.text()).toContain('我的猫')
    expect(wrapper.text()).toContain('Original source')
    wrapper.findComponent(NSelect).vm.$emit('update:value', 'project')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/content/passage/{id}/reading', expect.objectContaining({
      params: {
        path: { id: 'passage' },
        query: { project_id: 'project' },
      },
    }))
  })
  it.each(['en', 'zh-CN'] as const)('has localized unavailable and retry states (%s)', async (locale) => {
    client.GET.mockImplementation(async (path: string) => path.endsWith('/reading')
      ? fail(404)
      : ok(path === '/api/projects'
          ? { items: [] }
          : []))
    await setup('/reading/missing', locale)
    expect(wrapper.find('article').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').text()).toContain(locale === 'en'
      ? 'unavailable'
      : '不可用')
    client.GET.mockImplementation(async path => path.endsWith('/reading')
      ? ok(fixture())
      : ok(path === '/api/projects'
          ? { items: [], total: 0 }
          : []))
    await button(locale === 'en'
      ? 'Retry loading'
      : '重新加载').trigger('click')
    await flushPromises()
    expect(wrapper.find('article').exists()).toBe(true)
  })
  it('keeps the original passage without stale highlights when a new project fails', async () => {
    await setup()
    client.GET.mockResolvedValueOnce(fail())
    wrapper.findComponent(NSelect).vm.$emit('update:value', 'different-project')
    await flushPromises()
    expect(wrapper.find('article').text()).toBe('🙂 cat.\n bank unknown!')
    expect(wrapper.find('[data-state="selected"]').exists()).toBe(false)
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  })
  it('retains creation drafts after ingestion failure and retries successfully', async () => {
    await setup('/reading')
    const inputs = wrapper.findAllComponents(NInput)
    inputs[0]!.vm.$emit('update:value', 'Draft title')
    inputs[1]!.vm.$emit('update:value', 'Draft source')
    inputs[2]!.vm.$emit('update:value', 'Draft text.')
    await flushPromises()
    client.POST.mockResolvedValueOnce(fail()).mockResolvedValueOnce(ok(fixture()))
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(inputs[2]!.props('value')).toBe('Draft text.')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(client.POST).toHaveBeenLastCalledWith('/api/content/ingest', {
      body: {
        text: 'Draft text.',
        title: 'Draft title',
        source: 'Draft source',
        lang: 'en',
      },
    })
    expect(wrapper.find('article').exists()).toBe(true)
  })
})

describe('explicit inline lookup', () => {
  async function selectUnknown() {
    await setup()
    wrapper.findComponent(NSelect).vm.$emit('update:value', 'project')
    await flushPromises()
    await wrapper.find('[data-state="unlinked"]').trigger('click')
    await button('Look up word').trigger('click')
    await flushPromises()
    return wrapper.findComponent(ReadingLookup)
  }
  it('requires an explicit sense, preserves dismissed drafts and retries only a failed link', async () => {
    const lookup = await selectUnknown()
    const selector = lookup.findComponent(NSelect)
    expect(selector.props('options')).toHaveLength(2)
    expect(button('Add sense and link occurrence').attributes('disabled')).toBeDefined()
    selector.vm.$emit('update:value', JSON.stringify(candidate.lexemes[0]!.senses[1]!.id))
    await flushPromises()
    await button('Dismiss').trigger('click')
    await wrapper.find('[data-state="unlinked"]').trigger('click')
    expect(selector.props('value')).toBe(JSON.stringify(candidate.lexemes[0]!.senses[1]!.id))
    client.PUT.mockResolvedValueOnce(fail()).mockResolvedValueOnce(ok({ occurrences: [] }))
    await button('Add sense and link occurrence').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Your selection is kept')
    expect(wrapper.find('article').text()).toBe('🙂 cat.\n bank unknown!')
    await button('Retry add and link').trigger('click')
    await flushPromises()
    expect(client.POST.mock.calls.filter(([path]) => path === '/api/projects/{id}/dictionary')).toHaveLength(1)
    expect(client.PUT).toHaveBeenLastCalledWith('/api/content/sentence/{id}/occurrences', {
      params: {
        path: { id: 'second' },
      },
      body: {
        span: [5, 12],
        sense_id: 'chosen',
      },
    })
    expect(client.POST).toHaveBeenCalledWith('/api/projects/{id}/dictionary', {
      params: {
        path: { id: 'project' },
      },
      body: {
        lemma_key: ['en', 'bank'],
        selected_senses: [candidate.lexemes[0]!.senses[1]!.id],
      },
    })
  })
  it('preserves sense choice after add failure and handles empty/unavailable lookup', async () => {
    const lookup = await selectUnknown()
    lookup.findComponent(NSelect).vm.$emit('update:value', JSON.stringify(candidate.lexemes[0]!.senses[0]!.id))
    await flushPromises()
    client.POST.mockResolvedValueOnce(fail()).mockResolvedValueOnce(ok({
      selected_sense_ids: ['chosen'],
    }))
    await button('Add sense and link occurrence').trigger('click')
    await flushPromises()
    expect(client.PUT).not.toHaveBeenCalled()
    await button('Retry add and link').trigger('click')
    await flushPromises()
    expect(client.PUT).toHaveBeenCalledTimes(1)
    await wrapper.find('[data-state="unlinked"]').trigger('click')
    client.POST.mockResolvedValueOnce(ok({ candidates: [] }))
    await button('Look up word').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No dictionary candidates')
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await button('Look up word').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Your selection is kept')
  })
})
