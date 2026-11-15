import { mount } from '@vue/test-utils'
import { NDropdown } from 'naive-ui'
import { createPinia, disposePinia } from 'pinia'
import { afterEach, describe, expect, it } from 'vitest'
import { createAppI18n } from '@/i18n'
import { usePreferencesStore } from '@/stores/preferences'
import LocaleSwitch from './LocaleSwitch.vue'
import ThemeToggle from './ThemeToggle.vue'

const wrappers: ReturnType<typeof mount>[] = []
const instances: ReturnType<typeof createPinia>[] = []

afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  instances.splice(0).forEach(disposePinia)
  localStorage.clear()
})

function render(component: typeof LocaleSwitch | typeof ThemeToggle) {
  const pinia = createPinia()
  instances.push(pinia)
  const i18n = createAppI18n()
  const wrapper = mount(component, {
    global: {
      plugins: [pinia, i18n],
    },
  })
  wrappers.push(wrapper)
  return {
    wrapper,
    preferences: usePreferencesStore(pinia),
  }
}

describe('header preferences', () => {
  it('opens a plain language menu without changing language until an option is selected', async () => {
    const { wrapper, preferences } = render(LocaleSwitch)
    preferences.locale = 'en'
    await wrapper.get('button').trigger('click')
    expect(preferences.locale).toBe('en')
    const menu = wrapper.getComponent(NDropdown)
    expect(menu.props('options')).toEqual([
      { key: 'en', label: 'English' },
      { key: 'zh-CN', label: '简体中文' },
    ])
    menu.vm.$emit('select', 'zh-CN')
    expect(preferences.locale).toBe('zh-CN')
    menu.vm.$emit('select', 'en')
    expect(preferences.locale).toBe('en')
  })

  it('toggles repeatedly between light and dark without a system option', async () => {
    const { wrapper, preferences } = render(ThemeToggle)
    expect(preferences.theme).toBe('light')
    await wrapper.get('button').trigger('click')
    expect(preferences.theme).toBe('dark')
    await wrapper.get('button').trigger('click')
    expect(preferences.theme).toBe('light')
    await wrapper.get('button').trigger('click')
    expect(preferences.theme).toBe('dark')
  })
})
