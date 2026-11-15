import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import GraphLegend from '@/components/graph/GraphLegend.vue'
import GraphToolbar from '@/components/graph/GraphToolbar.vue'
import { createAppI18n } from '@/i18n'
import GraphExplorer from './GraphExplorer.vue'
import SenseRelations from './SenseRelations.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
vi.mock('@/components/graph/GraphCanvas.vue', () => ({
  default: {
    name: 'GraphCanvas',
    props: ['elements', 'focusId', 'layout'],
    emits: ['select', 'expand'],
    template: '<div data-testid="canvas-stub" />',
  },
}))
const lemma = {
  id: 'opaque:lemma/a',
  table: 'lemma',
  fields: { text: 'run', kind: 'word' },
}
const graph = {
  nodes: [lemma],
  edges: [],
  focus_id: lemma.id,
  depth: 1,
  direction: 'both',
  node_types: [],
  relation_types: [],
  node_limit: 300,
}
function ok(data: unknown) {
  return {
    data,
    response: new Response(),
  }
}
let wrapper: ReturnType<typeof mount>
async function setup(props = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/',
        component: { template: '<div />' },
      },
      {
        path: '/words/:lemmaId',
        name: 'word',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push('/')
  const i18n = createAppI18n()
  i18n.global.locale.value = 'en'
  wrapper = mount(GraphExplorer, {
    props,
    global: {
      plugins: [
        i18n,
        createPinia(),
        router,
      ],
    },
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => client.GET.mockImplementation((path: string) => Promise.resolve(ok(path === '/api/graph'
  ? graph
  : [lemma]))))
afterEach(() => {
  wrapper?.unmount()
  vi.resetAllMocks()
})
describe('bounded graph exploration', () => {
  it('loads seeds only, searches, selects focus and expands up to depth three', async () => {
    await setup()
    expect(client.GET.mock.calls.map(call => call[0])).toEqual(['/api/graph/seeds'])
    const toolbar = wrapper.findComponent(GraphToolbar)
    toolbar.vm.$emit('update:search', 'run')
    toolbar.vm.$emit('search')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/graph/seeds', expect.objectContaining({
      params: {
        query: { q: 'run', page: 1, page_size: 20 },
      },
    }))
    await wrapper.findAll('button').find(button => button.text() === 'run')!.trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/graph', expect.objectContaining({
      params: {
        query: expect.objectContaining({ focus_id: lemma.id, depth: 1 }),
      },
    }))
    const canvas = wrapper.findComponent({ name: 'GraphCanvas' })
    canvas.vm.$emit('select', lemma.id)
    canvas.vm.$emit('expand', lemma.id)
    await flushPromises()
    expect(client.GET.mock.calls.at(-1)?.[1].params.query.depth).toBe(2)
    wrapper.findComponent({ name: 'GraphCanvas' }).vm.$emit('expand', lemma.id)
    await flushPromises()
    expect(client.GET.mock.calls.at(-1)?.[1].params.query.depth).toBe(3)
    expect(wrapper.find('[data-testid="graph-selection"] button').attributes('disabled')).toBeDefined()
    const calls = client.GET.mock.calls.length
    toolbar.vm.$emit('update:layout', 'dagre')
    await flushPromises()
    expect(client.GET).toHaveBeenCalledTimes(calls)
    wrapper.findComponent(GraphLegend).vm.$emit('update:nodes', ['lemma'])
    await flushPromises()
    expect(client.GET.mock.calls.at(-1)?.[1].params.query.node_types).toEqual(['lemma'])
    wrapper.findComponent({ name: 'GraphCanvas' }).vm.$emit('expand', 'opaque:other')
    await flushPromises()
    expect(client.GET.mock.calls.at(-1)?.[1].params.query.focus_id).toBe('opaque:other')
  })

  it('renders recoverable too-large errors and filtered empty graphs', async () => {
    await setup({ initialFocus: lemma.id })
    client.GET.mockResolvedValueOnce({
      error: { code: 'graph.too_large' },
      response: new Response(null, { status: 413 }),
    })
    wrapper.findComponent(GraphToolbar).vm.$emit('update:depth', 3)
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('Reduce depth')
    expect(wrapper.find('[data-testid="canvas-stub"]').exists()).toBe(false)
    client.GET.mockResolvedValueOnce(ok({ ...graph, nodes: [] }))
    await wrapper.find('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No nodes match')
  })

  it('handles empty discovery and transport failure without loading a full graph', async () => {
    client.GET.mockResolvedValueOnce(ok([]))
    await setup()
    expect(wrapper.text()).toContain('No visible vocabulary')
    client.GET.mockRejectedValueOnce(new Error('offline'))
    wrapper.findComponent(GraphToolbar).vm.$emit('search')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(client.GET.mock.calls.some(call => call[0] === '/api/graph')).toBe(false)
  })

  it('refreshes the same bounded neighborhood after relation changes without losing the selection', async () => {
    const sense = {
      id: 'sense',
      table: 'sense',
      fields: { definition: 'Meaning' },
    }
    client.GET.mockImplementation((path: string) => Promise.resolve(ok(path === '/api/graph'
      ? {
          ...graph,
          nodes: [lemma, sense],
        }
      : [])))
    await setup({ initialFocus: lemma.id })
    wrapper.findComponent({ name: 'GraphCanvas' }).vm.$emit('select', sense.id)
    await flushPromises()
    const editor = wrapper.findComponent(SenseRelations)
    expect(editor.props('senseId')).toBe(sense.id)
    editor.vm.$emit('changed')
    await flushPromises()
    const graphCalls = client.GET.mock.calls.filter(call => call[0] === '/api/graph')
    expect(graphCalls).toHaveLength(2)
    expect(graphCalls[1]?.[1].params.query).toEqual(graphCalls[0]?.[1].params.query)
    expect(wrapper.findComponent(SenseRelations).props('senseId')).toBe(sense.id)
  })
})
