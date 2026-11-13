import { mount } from '@vue/test-utils'
import { NConfigProvider } from 'naive-ui'
import { createPinia, disposePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory } from 'vue-router'
import App from '@/app/App.vue'
import { createAppRouter } from '@/app/router'
import LocaleSwitch from '@/components/app/LocaleSwitch.vue'
import ThemeToggle from '@/components/app/ThemeToggle.vue'
import { darkThemeOverrides, themeOverrides } from '@/design/naive-theme'
import { createAppI18n } from '@/i18n'
import { usePreferencesStore } from '@/stores/preferences'

describe('app', () => {
  it('syncs controls, Naive theme, CSS theme and language metadata', async () => {
    localStorage.clear()
    const i18n = createAppI18n()
    const pinia = createPinia()
    const router = createAppRouter(createMemoryHistory())
    await router.push('/projects')
    await router.isReady()
    const wrapper = mount(App, {
      global: {
        plugins: [pinia, i18n, router],
      },
    })

    expect(wrapper.get('h1').text()).toBe('项目')
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(document.title).toBe('PandaWords')

    await wrapper.findComponent(LocaleSwitch).get('button').trigger('click')
    await nextTick()

    expect(wrapper.get('h1').text()).toBe('Projects')
    expect(document.documentElement.lang).toBe('en')
    expect(document.title).toBe('PandaWords')
    const preferences = usePreferencesStore(pinia)
    preferences.theme = 'light'
    await nextTick()
    expect(wrapper.findComponent(NConfigProvider).props('theme')).toBeNull()
    expect(wrapper.findComponent(NConfigProvider).props('themeOverrides')).toEqual(themeOverrides)
    await wrapper.findComponent(ThemeToggle).get('button').trigger('click')
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(wrapper.findComponent(NConfigProvider).props('theme')).toBeTruthy()
    expect(wrapper.findComponent(NConfigProvider).props('themeOverrides')).toEqual(darkThemeOverrides)
    await router.push('/login')
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.get('h1').text()).toBe('Sign in')
    wrapper.unmount()
    disposePinia(pinia)
  })
})
