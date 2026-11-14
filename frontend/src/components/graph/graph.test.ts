import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAppI18n } from '@/i18n'
import { usePreferencesStore } from '@/stores/preferences'
import { graphStyle } from './cytoscape-style'
import GraphCanvas from './GraphCanvas.vue'
import GraphLegend from './GraphLegend.vue'
import GraphToolbar from './GraphToolbar.vue'
import { presentGraph, presentNode } from './types'

const renderer = vi.hoisted(() => ({
  add: vi.fn(),
  remove: vi.fn(),
  run: vi.fn(),
  style: vi.fn(),
  fit: vi.fn(),
  resize: vi.fn(),
  destroy: vi.fn(),
  on: vi.fn(),
  zoom: vi.fn(),
  center: vi.fn(),
  layout: vi.fn(),
}))
vi.mock('cytoscape', () => ({
  default: Object.assign(() => ({
    ...renderer,
    elements: () => ({ remove: renderer.remove }),
    layout: (options: unknown) => {
      renderer.layout(options)
      return { run: renderer.run }
    },
  }), {
    use: vi.fn(),
  }),
}))
function global() {
  return {
    plugins: [
      createAppI18n(),
      createPinia(),
    ],
  }
}
const node = { id: 'opaque/lemma', label: 'run', type: 'lemma' as const }
afterEach(() => vi.clearAllMocks())

describe('shared graph components', () => {
  it('caps sparse automatic and explicit fitting without enlarging dense graph fits', () => {
    const wrapper = mount(GraphCanvas, {
      props: {
        elements: {
          nodes: [node],
          edges: [],
        },
      },
      global: global(),
    })
    const options = renderer.layout.mock.calls.at(-1)![0]
    expect(options.fit).toBe(false)
    renderer.zoom.mockReturnValue(6)
    options.stop()
    expect(renderer.zoom).toHaveBeenLastCalledWith(1)
    expect(renderer.center).toHaveBeenCalledOnce()
    renderer.zoom.mockClear().mockReturnValue(0.4)
    wrapper.vm.fit()
    expect(renderer.zoom.mock.calls).toEqual([[]])
    wrapper.unmount()
  })
  it('supports canvas pointer and accessible keyboard/touch selection, expansion, theme updates and cleanup', async () => {
    const wrapper = mount(GraphCanvas, {
      props: {
        elements: {
          nodes: [node],
          edges: [],
        },
        focusId: node.id,
      },
      global: global(),
    })
    const buttons = wrapper.findAll('button')
    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('select')?.[0]).toEqual([node.id])
    expect(wrapper.emitted('expand')?.[0]).toEqual([node.id])
    expect(buttons[0]!.attributes('aria-pressed')).toBe('true')
    expect(buttons[1]!.attributes('aria-label')).toBeTruthy()
    const pointerSelect = renderer.on.mock.calls.find(call => call[0] === 'tap')!
    pointerSelect[2]({
      target: {
        id: () => node.id,
      },
    })
    expect(wrapper.emitted('select')).toHaveLength(2)
    usePreferencesStore().theme = 'dark'
    await flushPromises()
    expect(renderer.style).toHaveBeenLastCalledWith(graphStyle('dark'))
    expect(graphStyle('dark')).not.toEqual(graphStyle('light'))
    wrapper.unmount()
    expect(renderer.destroy).toHaveBeenCalledOnce()
  })

  it('emits layout/depth/direction/search/fit and legend filter controls with labels', async () => {
    const wrapper = mount(GraphToolbar, {
      props: {
        layout: 'fcose',
        depth: 1,
        search: '',
        direction: 'both',
      },
      global: global(),
    })
    const selects = wrapper.findAllComponents({ name: 'Select' })
    expect(selects).toHaveLength(3)
    selects[0]!.vm.$emit('update:value', 'dagre')
    selects[1]!.vm.$emit('update:value', 3)
    selects[2]!.vm.$emit('update:value', 'outgoing')
    expect(wrapper.emitted('update:layout')?.[0]).toEqual(['dagre'])
    expect(wrapper.emitted('update:depth')?.[0]).toEqual([3])
    expect(wrapper.emitted('update:direction')?.[0]).toEqual(['outgoing'])
    expect(selects.every(select => !!select.attributes('aria-label'))).toBe(true)
    await wrapper.find('input').setValue('run')
    await wrapper.find('input').trigger('keyup.enter')
    expect(wrapper.emitted('search')).toHaveLength(1)
    await wrapper.findAll('button').at(-1)!.trigger('click')
    expect(wrapper.emitted('fit')).toHaveLength(1)
    wrapper.unmount()
    const legend = mount(GraphLegend, {
      props: { nodes: [], relations: [] },
      global: global(),
    })
    await legend.find('button').trigger('click')
    expect(legend.emitted('update:nodes')?.[0]).toEqual([
      ['lemma'],
    ])
    expect(legend.findAll('[role="group"]')).toHaveLength(2)
    legend.unmount()
  })

  it('rejects invalid labels, oversized results, duplicate nodes and dangling opaque edges', () => {
    const lemma = {
      id: 'opaque/lemma',
      table: 'lemma',
      fields: { text: 'run', kind: 'word' },
    } as Parameters<typeof presentNode>[0]
    expect(presentNode(lemma)).toMatchObject(node)
    expect(() => presentNode({ ...lemma, fields: {} } as typeof lemma)).toThrow()
    expect(() => presentGraph({
      nodes: Array.from<typeof lemma>({ length: 301 }).fill(lemma),
      edges: [],
    })).toThrow()
    expect(() => presentGraph({
      nodes: [lemma, lemma],
      edges: [],
    })).toThrow()
    expect(() => presentGraph({
      nodes: [lemma],
      edges: [
        {
          id: 'edge',
          table: 'has_sense',
          start: lemma.id,
          end: 'missing',
          fields: {},
        },
      ],
    })).toThrow()
  })
})
