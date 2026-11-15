import type { Component } from 'vue'
import type { ExercisePrompt } from './types'
import { mount } from '@vue/test-utils'
import { NButton } from 'naive-ui'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createAppI18n } from '@/i18n'
import ChoiceGrid from './ChoiceGrid.vue'
import ExerciseShell from './ExerciseShell.vue'
import RatingBar from './RatingBar.vue'
import ReviewProgress from './ReviewProgress.vue'
import TypedAnswerInput from './TypedAnswerInput.vue'

const prompt: ExercisePrompt = {
  text: 'Choose a word',
  input: 'choice',
  choices: [
    { id: 'opaque-bank', label: 'bank' },
    { id: 'opaque-river', label: 'river' },
    { id: 'opaque-tree', label: 'tree' },
    { id: 'opaque-book', label: 'book' },
  ],
}
const wrappers: { unmount: () => void }[] = []
function render(component: Component, props: Record<string, unknown> = {}, locale: 'en' | 'zh-CN' = 'en') {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(component, {
    props,
    attachTo: document.body,
    global: {
      plugins: [i18n],
    },
  })
  wrappers.push(wrapper)
  return wrapper
}
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.restoreAllMocks()
})

describe('choice controls', () => {
  it.each([2, 3, 4])('selects opaque answers using click and scoped keys with %i choices', async (count) => {
    const wrapper = render(ChoiceGrid, {
      choices: prompt.choices.slice(0, count),
    })
    expect(wrapper.findAll('button')).toHaveLength(count)
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['opaque-river'])
    await wrapper.trigger('keydown', {
      key: String(count),
    })
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([prompt.choices[count - 1]!.id])
    await wrapper.setProps({ modelValue: prompt.choices[count - 1]!.id })
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toHaveLength(1)
    expect(wrapper.findAll('button')[count - 1]!.attributes('aria-pressed')).toBe('true')
    await wrapper.trigger('keydown', { key: '1', repeat: true })
    await wrapper.trigger('keydown', { key: '1', ctrlKey: true })
    expect(wrapper.emitted('update:modelValue')).toHaveLength(2)
    await wrapper.setProps({ disabled: true })
    await wrapper.trigger('keydown', { key: '1' })
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toHaveLength(2)
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  it('does not submit missing choices or let events reach an enclosing rating scope', async () => {
    const wrapper = render(defineComponent({
      components: { ChoiceGrid, RatingBar },
      setup: () => ({ prompt }),
      template: '<div><RatingBar :auto-rating="3" /><ChoiceGrid :choices="prompt.choices" /></div>',
    }))
    const outer = vi.fn()
    wrapper.element.addEventListener('keydown', outer)
    const grid = wrapper.getComponent(ChoiceGrid)
    await grid.trigger('keydown', { key: 'Enter' })
    expect(grid.emitted('submit')).toBeUndefined()
    await grid.trigger('keydown', { key: '2' })
    expect(outer).not.toHaveBeenCalled()
    expect(wrapper.getComponent(RatingBar).emitted('change')).toBeUndefined()
    expect(wrapper.getComponent(RatingBar).emitted('confirm')).toBeUndefined()
  })
})

describe('typed recall', () => {
  it('labels the actual input, preserves original text, ignores IME Enter and displays server feedback', async () => {
    const wrapper = render(TypedAnswerInput)
    const input = wrapper.get('input')
    expect(wrapper.get('label').attributes('for')).toBe(input.attributes('id'))
    await input.setValue(' Banck ')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([' Banck '])
    await wrapper.setProps({ modelValue: ' Banck ' })
    await input.trigger('keydown', { key: 'Enter', isComposing: true })
    expect(wrapper.emitted('submit')).toBeUndefined()
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toHaveLength(1)
    await wrapper.setProps({
      feedback: { correct: false, answer: 'bank' },
    })
    expect(wrapper.get('del').text()).toBe('Banck')
    expect(wrapper.get('ins').text()).toBe('bank')
    expect(input.attributes('aria-describedby')).toBe(wrapper.get('div[id$="-feedback"]').attributes('id'))
    expect(input.attributes('disabled')).toBeDefined()
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toHaveLength(1)
  })

  it('does not submit empty input or disabled input', async () => {
    const wrapper = render(TypedAnswerInput, { modelValue: '   ' })
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    await wrapper.setProps({ modelValue: 'bank', disabled: true })
    await wrapper.get('input').trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('submit')).toBeUndefined()
  })
})

describe('server-driven exercise frame', () => {
  it('emits the exact answer with monotonic time and hint intent, then shows server feedback without grading locally', async () => {
    const clock = vi.spyOn(performance, 'now').mockReturnValue(100)
    const wrapper = render(ExerciseShell, { attemptId: 'first', prompt })
    await nextTick()
    expect(document.activeElement).toBe(wrapper.get('button').element)
    await wrapper.trigger('keydown', { key: 'h' })
    expect(wrapper.emitted('hint')).toEqual([[]])
    expect(wrapper.find('p[role="status"]').exists()).toBe(false)
    await wrapper.setProps({ hint: 'Starts with b' })
    expect(wrapper.get('p[role="status"]').text()).toContain('Starts with b')
    await wrapper.trigger('keydown', { key: 'h' })
    expect(wrapper.emitted('hint')).toHaveLength(1)
    await wrapper.getComponent(ChoiceGrid).trigger('keydown', { key: '2' })
    clock.mockReturnValue(347.9)
    await wrapper.getComponent(ChoiceGrid).trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('answered')).toEqual([
      [
        { answer: 'opaque-river', duration_ms: 247 },
      ],
    ])
    expect(wrapper.findComponent(RatingBar).exists()).toBe(false)
    await wrapper.getComponent(ChoiceGrid).trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('answered')).toHaveLength(1)
    await wrapper.setProps({
      feedback: { correct: true, answer: 'server answer' },
      autoRating: 2,
    })
    expect(wrapper.text()).toContain('Correct')
    expect(wrapper.text()).toContain('server answer')
    expect(wrapper.getComponent(RatingBar).props('autoRating')).toBe(2)
    await nextTick()
    expect(document.activeElement?.getAttribute('aria-pressed')).toBe('true')
    await wrapper.getComponent(RatingBar).trigger('keydown', { key: '4' })
    await wrapper.getComponent(RatingBar).trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('confirm')).toEqual([
      [4],
    ])
    expect(wrapper.emitted('answered')).toHaveLength(1)
  })

  it('resets time and answer for a new attempt, supports give up, and prevents actions while submitting or requesting hints', async () => {
    const clock = vi.spyOn(performance, 'now').mockReturnValue(100)
    const wrapper = render(ExerciseShell, { attemptId: 'first', prompt })
    await wrapper.getComponent(ChoiceGrid).trigger('keydown', { key: '1' })
    await wrapper.setProps({ submitting: true })
    expect(wrapper.findAllComponents(NButton).every(button => button.props('disabled'))).toBe(true)
    await wrapper.trigger('keydown', { key: 'h' })
    await wrapper.getComponent(ChoiceGrid).trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('answered')).toBeUndefined()
    expect(wrapper.emitted('hint')).toBeUndefined()
    await wrapper.setProps({ submitting: false, hintLoading: true })
    expect(wrapper.attributes('aria-busy')).toBe('true')
    await wrapper.trigger('keydown', { key: 'h' })
    expect(wrapper.emitted('hint')).toBeUndefined()
    clock.mockReturnValue(500)
    await wrapper.setProps({ attemptId: 'second', hintLoading: false })
    expect(wrapper.getComponent(ChoiceGrid).props('modelValue')).toBe('')
    clock.mockReturnValue(600)
    const giveUp = wrapper.findAll('button').find(button => button.text() === 'Give up')!
    await giveUp.trigger('click')
    expect(wrapper.emitted('giveUp')).toEqual([
      [
        { duration_ms: 100 },
      ],
    ])
    expect(wrapper.emitted('answered')).toBeUndefined()
  })

  it('leaves letters, digits and spaces in text fields alone and localizes the controls', async () => {
    const wrapper = render(ExerciseShell, {
      attemptId: 'text',
      prompt: { text: 'Type', input: 'text', choices: [] },
    }, 'zh-CN')
    const input = wrapper.get('input')
    for (const key of ['h', '1', ' ', 'Escape'])
      await input.trigger('keydown', { key })
    expect(wrapper.emitted('hint')).toBeUndefined()
    expect(wrapper.emitted('exit')).toBeUndefined()
    expect(wrapper.emitted('audio')).toBeUndefined()
    await input.setValue(' Hint 1 ')
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('answered')?.[0]?.[0]).toMatchObject({ answer: ' Hint 1 ' })
    expect(wrapper.text()).toContain('提交答案')
  })
})

describe('rating and progress', () => {
  it('preselects the auto-rating, supports click and keys, and blocks confirmation while loading', async () => {
    const wrapper = render(RatingBar, { autoRating: 3 })
    expect(wrapper.findAll('button').map(button => button.attributes('aria-pressed'))).toEqual([
      'false',
      'false',
      'true',
      'false',
      undefined,
    ])
    await wrapper.findAll('button')[1]!.trigger('click')
    expect(wrapper.emitted('change')).toEqual([
      [2],
    ])
    await wrapper.trigger('keydown', { key: ' ' })
    expect(wrapper.emitted('confirm')).toEqual([
      [2],
    ])
    await wrapper.setProps({ autoRating: 1 })
    expect(wrapper.findAll('button')[0]!.attributes('aria-pressed')).toBe('true')
    await wrapper.setProps({ loading: true })
    await wrapper.trigger('keydown', { key: '4' })
    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('change')).toHaveLength(1)
    expect(wrapper.emitted('confirm')).toHaveLength(1)
  })

  it('shows explicit server counts, including empty and complete sessions', async () => {
    const wrapper = render(ReviewProgress, {
      done: 3,
      remaining: 7,
      newCount: 2,
      reviewCount: 5,
    })
    expect(wrapper.get('progress').attributes()).toMatchObject({ 'value': '3', 'max': '10', 'aria-label': 'Review progress' })
    expect(wrapper.text()).toContain('3 done · 7 remaining')
    expect(wrapper.text()).toContain('2 new · 5 review')
    await wrapper.setProps({ done: 10, remaining: 0 })
    expect(wrapper.get('progress').attributes('value')).toBe('10')
    await wrapper.setProps({
      done: 0,
      remaining: 0,
      newCount: 0,
      reviewCount: 0,
    })
    expect(wrapper.get('progress').attributes('max')).toBe('1')
    expect(wrapper.get('progress').attributes('aria-valuetext')).toBe('0 done · 0 remaining')
  })
})
