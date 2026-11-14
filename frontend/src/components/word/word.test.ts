import type { Component } from 'vue'
import type { LexemeView } from './types'
import { flushPromises, mount } from '@vue/test-utils'
import { NButton, NCheckbox } from 'naive-ui'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createAppI18n } from '@/i18n'
import AudioButton from './AudioButton.vue'
import LemmaTree from './LemmaTree.vue'
import NoteEditor from './NoteEditor.vue'
import PronunciationChip from './PronunciationChip.vue'
import SenseItem from './SenseItem.vue'
import SenseSelectList from './SenseSelectList.vue'

const candidates: LexemeView[] = [
  {
    id: 'noun',
    pos: 'noun',
    senses: [
      { id: 'common', definition: 'Common definition', common: true },
      { id: 'rare', definition: 'Rare definition' },
      {
        id: 'hidden',
        definition: 'Hidden definition',
        common: true,
        hidden: true,
      },
    ],
  },
  {
    id: 'verb',
    pos: 'verb',
    senses: [
      { id: 'verb-common', definition: 'Common verb', common: true },
    ],
  },
]

const wrappers: { unmount: () => void }[] = []
function render(component: Component, props: Record<string, unknown> = {}, locale: 'en' | 'zh-CN' = 'en') {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(component, {
    props,
    global: {
      plugins: [i18n],
    },
  })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('controlled audio', () => {
  it('only emits requests when playback is managed externally', async () => {
    const play = vi.fn()
    vi.stubGlobal('Audio', class {
      play = play
      pause = vi.fn()
    })
    const wrapper = render(PronunciationChip, {
      ipa: 'rʌn',
      accent: 'US',
      audioUrl: 'blob:external',
      playbackState: 'stopped',
    })
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('play')).toEqual([
      ['blob:external'],
    ])
    expect(play).not.toHaveBeenCalled()
    await wrapper.setProps({ playbackState: 'playing' })
    expect(wrapper.get('button').attributes('aria-pressed')).toBe('true')
    await wrapper.get('button').trigger('click')
    expect(wrapper.emitted('play')).toHaveLength(2)
    expect(play).not.toHaveBeenCalled()
  })
})

describe('word sense selection', () => {
  it('defaults to common visible senses across lexemes and preserves explicit empty selection', async () => {
    const wrapper = render(SenseSelectList, { candidates })
    expect(wrapper.emitted('update:selected')).toEqual([
      [
        ['common', 'verb-common'],
      ],
    ])
    expect(wrapper.findAllComponents(NCheckbox).map(box => box.props('checked'))).toEqual([true, false, false, true])
    expect(wrapper.findAllComponents(NCheckbox)[2]!.props('disabled')).toBe(true)
    expect(wrapper.findAllComponents(NCheckbox)[2]!.attributes('aria-disabled')).toBe('true')
    await wrapper.setProps({ selected: [] })
    expect(wrapper.findAllComponents(NCheckbox).every(box => !box.props('checked'))).toBe(true)
    wrapper.findAllComponents(NCheckbox)[1]!.vm.$emit('update:checked', true)
    expect(wrapper.emitted('update:selected')?.at(-1)).toEqual([
      ['rare'],
    ])
  })

  it('updates controlled selections without replacing previous choices or mutating candidates', async () => {
    const wrapper = render(SenseSelectList, {
      candidates,
      selected: ['rare', 'verb-common'],
    })
    expect(wrapper.emitted('update:selected')).toBeUndefined()
    wrapper.findAllComponents(NCheckbox)[0]!.vm.$emit('update:checked', true)
    expect(wrapper.emitted('update:selected')).toEqual([
      [
        ['rare', 'verb-common', 'common'],
      ],
    ])
    await wrapper.setProps({
      selected: ['common', 'rare'],
    })
    wrapper.findAllComponents(NCheckbox)[0]!.vm.$emit('update:checked', false)
    expect(wrapper.emitted('update:selected')?.at(-1)).toEqual([
      ['rare'],
    ])
    expect(candidates[0]!.senses[0]!.common).toBe(true)
  })

  it('initializes async uncontrolled candidates and localizes the empty state', async () => {
    const wrapper = render(SenseSelectList, { candidates: [] }, 'zh-CN')
    expect(wrapper.text()).toContain('暂无候选义项')
    await wrapper.setProps({ candidates })
    expect(wrapper.emitted('update:selected')?.at(-1)).toEqual([
      ['common', 'verb-common'],
    ])
  })
})

describe('effective sense views', () => {
  it('shows hidden and customized markers, expands examples, and emits reversible actions', async () => {
    const sense = {
      id: 'sense',
      definition: 'Effective definition',
      gloss: '自定义释义',
      hidden: true,
      overridden: true,
      examples: [
        { text: 'Example sentence.', translation: '例句。' },
      ],
    }
    const wrapper = render(SenseItem, { sense, editable: true })
    expect(wrapper.text()).toContain('Customized')
    expect(wrapper.text()).toContain('Hidden')
    expect(wrapper.text()).not.toContain('Example sentence.')
    await wrapper.findAllComponents(NButton)[0]!.trigger('click')
    expect(wrapper.text()).toContain('Example sentence.')
    expect(wrapper.text()).toContain('例句。')
    expect(wrapper.findAllComponents(NButton)[0]!.attributes('aria-expanded')).toBe('true')
    await wrapper.findAllComponents(NButton)[1]!.trigger('click')
    await wrapper.findAllComponents(NButton)[2]!.trigger('click')
    await wrapper.findAllComponents(NButton)[3]!.trigger('click')
    expect(wrapper.emitted('edit')).toEqual([
      ['sense'],
    ])
    expect(wrapper.emitted('hide')).toEqual([
      ['sense', false],
    ])
    expect(wrapper.emitted('note')).toEqual([
      ['sense'],
    ])
    await wrapper.setProps({ hidden: false, editable: false })
    expect(wrapper.attributes('data-hidden')).toBe('false')
    expect(wrapper.text()).not.toContain('Hidden')
    expect(wrapper.findAllComponents(NButton)).toHaveLength(1)
  })

  it('renders expanded tree content and emits controlled expansion and selection', async () => {
    const wrapper = render(LemmaTree, {
      items: [
        {
          lemma: { id: 'bank', text: 'bank', kind: 'word' },
          lexemes: candidates,
        },
      ],
      expandedKeys: ['bank', 'noun'],
      selectedKeys: [],
    })
    expect(wrapper.text()).toContain('bank')
    expect(wrapper.text()).toContain('Common definition')
    const { NTree } = await import('naive-ui')
    wrapper.findComponent(NTree).vm.$emit('update:expandedKeys', ['bank'])
    wrapper.findComponent(NTree).vm.$emit('update:selectedKeys', ['rare'])
    expect(wrapper.emitted('update:expandedKeys')).toEqual([
      [
        ['bank'],
      ],
    ])
    expect(wrapper.emitted('update:selectedKeys')).toEqual([
      [
        ['rare'],
      ],
    ])
  })

  it('edits notes through a controlled model and emits target-aware saves without persistence', async () => {
    const wrapper = render(NoteEditor, { target: 'sense:1', kind: 'mnemonic', modelValue: 'Remember this' })
    expect(wrapper.find('label').attributes('for')).toBe(wrapper.find('textarea').attributes('id'))
    await wrapper.find('textarea').setValue('New mnemonic')
    expect(wrapper.emitted('update:modelValue')).toEqual([
      ['New mnemonic'],
    ])
    await wrapper.setProps({ modelValue: 'New mnemonic' })
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('save')).toEqual([
      [
        { target: 'sense:1', kind: 'mnemonic', text: 'New mnemonic' },
      ],
    ])
    await wrapper.setProps({ saving: true })
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('save')).toHaveLength(1)
    expect(wrapper.find('textarea').attributes('disabled')).toBeDefined()
  })
})

describe('audio controls', () => {
  it('shares one player, stops previous playback, cleans up and reports failed playback', async () => {
    const media = {
      src: '',
      play: vi.fn().mockResolvedValue(undefined),
      pause: vi.fn(),
      onended: undefined as (() => void) | undefined,
      onerror: undefined as (() => void) | undefined,
    }
    const Audio = vi.fn(class {
      constructor() {
        return media
      }
    })
    vi.stubGlobal('Audio', Audio)
    const first = render(AudioButton, { src: 'first.wav' })
    const second = render(AudioButton, { src: 'second.wav' })
    await first.find('button').trigger('click')
    expect(first.emitted('play')).toEqual([
      ['first.wav'],
    ])
    expect(first.find('button').attributes('aria-label')).toBe('Stop pronunciation')
    await second.find('button').trigger('click')
    expect(Audio).toHaveBeenCalledTimes(1)
    expect(media.src).toBe('second.wav')
    expect(media.pause).toHaveBeenCalledTimes(2)
    expect(first.find('button').attributes('aria-pressed')).toBe('false')
    await second.find('button').trigger('click')
    expect(second.find('button').attributes('aria-pressed')).toBe('false')
    media.play.mockRejectedValueOnce(new Error('blocked'))
    await second.find('button').trigger('click')
    await flushPromises()
    expect(second.find('[role="status"]').text()).toContain('could not be played')
    expect(second.emitted('error')).toHaveLength(1)
    await second.find('button').trigger('click')
    media.onerror?.()
    await flushPromises()
    expect(second.emitted('error')).toHaveLength(2)
    await second.find('button').trigger('click')
    media.onended?.()
    await flushPromises()
    expect(second.find('button').attributes('aria-pressed')).toBe('false')
    let rejectOld: (error: Error) => void = () => {}
    media.play.mockImplementationOnce(() => new Promise<undefined>((_resolve, reject) => {
      rejectOld = reject
    }))
    await second.find('button').trigger('click')
    await second.setProps({ src: 'replacement.wav' })
    expect(second.find('button').attributes('aria-pressed')).toBe('false')
    await second.find('button').trigger('click')
    rejectOld(new Error('superseded'))
    await flushPromises()
    expect(second.emitted('error')).toHaveLength(2)
    expect(second.find('button').attributes('aria-pressed')).toBe('true')
    const pausesBeforeUnmount = media.pause.mock.calls.length
    second.unmount()
    expect(media.pause).toHaveBeenCalledTimes(pausesBeforeUnmount + 1)
  })

  it('supports event-only play and disabled pronunciation controls with localized labels', async () => {
    const eventOnly = render(AudioButton)
    await eventOnly.find('button').trigger('click')
    expect(eventOnly.emitted('play')).toEqual([
      [undefined],
    ])
    const chip = render(PronunciationChip, { ipa: 'bæŋk', accent: 'US', disabled: true }, 'zh-CN')
    expect(chip.text()).toContain('美音')
    expect(chip.text()).toContain('/bæŋk/')
    expect(chip.find('button').attributes('aria-label')).toBe('播放发音')
    await chip.find('button').trigger('click')
    expect(chip.emitted('play')).toBeUndefined()
  })
})
