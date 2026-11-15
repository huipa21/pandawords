import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NDropdown } from 'naive-ui'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { createMemoryHistory } from 'vue-router'
import App from '@/app/App.vue'
import { createAppRouter } from '@/app/router'
import LocaleSwitch from '@/components/app/LocaleSwitch.vue'
import ThemeToggle from '@/components/app/ThemeToggle.vue'
import { darkThemeOverrides, themeOverrides } from '@/design/naive-theme'
import { mockSession } from '@/features/auth/testHarness'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { usePreferencesStore } from '@/stores/preferences'

vi.mock('@/api/client', async original => ({
  ...await original<typeof import('@/api/client')>(),
  api: {
    GET: vi.fn(async () => ({
      data: {
        items: [],
        total: 0,
        page: 1,
        page_size: 20,
      },
      response: new Response(null, { status: 200 }),
    })),
  },
}))

describe('app', () => {
  it('only registers the design route in development', () => {
    try {
      vi.stubEnv('DEV', false)
      const production = createAppRouter(createMemoryHistory())
      expect(production.hasRoute('design')).toBe(false)
      expect(production.resolve('/dev/design').name).toBe('not-found')
      vi.stubEnv('DEV', true)
      expect(createAppRouter(createMemoryHistory()).hasRoute('design')).toBe(true)
    }
    finally {
      vi.unstubAllEnvs()
    }
  })

  it('renders both preview themes and translates its local messages with the app', async () => {
    localStorage.clear()
    const pinia = createPinia()
    setActivePinia(pinia)
    mockSession()
    const router = createAppRouter(createMemoryHistory())
    await router.push('/dev/design')
    await router.isReady()
    const wrapper = mount(App, {
      global: {
        plugins: [
          pinia,
          createAppI18n(),
          router,
        ],
        stubs: { GraphCanvas: true },
      },
    })
    try {
      expect(wrapper.get('h1').text()).toBe('设计系统实验室')
      const panels = wrapper.findAll('[data-preview-theme]')
      expect(panels).toHaveLength(2)
      expect(panels[0]!.attributes('style')).toContain('--pw-color-primary: #1976D2')
      expect(panels[1]!.attributes('style')).toContain('--pw-color-primary: #64B5F6')
      await wrapper.findComponent(LocaleSwitch).get('button').trigger('click')
      wrapper.findComponent(LocaleSwitch).getComponent(NDropdown).vm.$emit('select', 'en')
      await nextTick()
      expect(wrapper.get('h1').text()).toBe('Design system laboratory')
      expect(wrapper.text()).toContain('Naive UI playground')
      await wrapper.get('#sample-light').setValue('connection')
      expect((wrapper.get('#sample-dark').element as HTMLInputElement).value).toBe('connection')
    }
    finally {
      wrapper.unmount()
      disposePinia(pinia)
      vi.unstubAllGlobals()
    }
  }, 20_000)

  it('syncs controls, Naive theme, CSS theme and language metadata', async () => {
    localStorage.clear()
    const i18n = createAppI18n()
    const pinia = createPinia()
    setActivePinia(pinia)
    mockSession()
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
    wrapper.findComponent(LocaleSwitch).getComponent(NDropdown).vm.$emit('select', 'en')
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
    useAuthStore(pinia).reset()
    await flushPromises()
    await router.push('/login')
    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.get('h1').text()).toBe('Sign in')
    wrapper.unmount()
    disposePinia(pinia)
    vi.unstubAllGlobals()
  })
})
