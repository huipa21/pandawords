import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NDropdown, NMessageProvider } from 'naive-ui'
import { createPinia, disposePinia } from 'pinia'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import AppHeader from '@/components/app/AppHeader.vue'
import { authPayload } from '@/features/auth/testHarness'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import LocaleSwitch from './LocaleSwitch.vue'
import ThemeToggle from './ThemeToggle.vue'

const wrappers: ReturnType<typeof mount>[] = []
const piniaInstances: ReturnType<typeof createPinia>[] = []

afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  piniaInstances.splice(0).forEach(disposePinia)
  vi.restoreAllMocks()
})

describe('app header', () => {
  it('shows the decorative panda before the localized brand and preserves navigation actions', async () => {
    const pinia = createPinia()
    piniaInstances.push(pinia)
    const auth = useAuthStore(pinia)
    auth.accessToken = 'test-access'
    auth.user = authPayload().user

    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['projects', 'profile', 'login'].map(path => ({
        path: `/${path}`,
        component: { template: '<div />' },
      })),
    })
    const i18n = createAppI18n()
    i18n.global.locale.value = 'en'
    const root = defineComponent({
      setup: () => () => h(NConfigProvider, null, {
        default: () => h(NMessageProvider, null, {
          default: () => h(AppHeader),
        }),
      }),
    })
    const wrapper = mount(root, {
      global: {
        plugins: [pinia, i18n, router],
      },
    })
    wrappers.push(wrapper)

    const brand = wrapper.get('a[href="/projects"]')
    const badge = brand.get('[aria-hidden="true"]')
    expect(brand.text().trim()).toBe(i18n.global.t('app.name'))
    expect(brand.element.firstElementChild).toBe(badge.element)
    expect(badge.element.querySelector('svg')).not.toBeNull()
    expect(wrapper.find('a[href="/change-password"]').exists()).toBe(false)
    expect(wrapper.find(`button[aria-label="${i18n.global.t('auth.logout')}"]`).exists()).toBe(false)
    expect(wrapper.get(`button[aria-label="${i18n.global.t('profile.accountMenu')}"]`).text()).toBe('L')
    expect(wrapper.findComponent(ThemeToggle).exists()).toBe(true)
    expect(wrapper.findComponent(LocaleSwitch).exists()).toBe(true)

    const logout = vi.spyOn(auth, 'logout').mockResolvedValue()
    const account = wrapper.findAllComponents(NDropdown).at(-1)!
    account.vm.$emit('select', 'profile')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/profile')
    account.vm.$emit('select', 'logout')
    await flushPromises()

    expect(logout).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/login')
  })
})
