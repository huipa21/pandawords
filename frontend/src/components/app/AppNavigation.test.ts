import { mount } from '@vue/test-utils'
import { createPinia, disposePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { authPayload } from '@/features/auth/testHarness'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import AppNavigation from './AppNavigation.vue'

const paths = [
  '/projects',
  '/review',
  '/words',
  '/reading',
  '/settings',
  '/admin/users',
  '/admin/backup',
]
const emptyPage = {
  render: () => null,
}

async function setup(options: {
  path?: string
  mobile?: boolean
  role?: 'user' | 'admin'
  locale?: 'en' | 'zh-CN'
} = {}) {
  const pinia = createPinia()
  useAuthStore(pinia).user = authPayload({ role: options.role ?? 'user' }).user
  const router = createRouter({
    history: createMemoryHistory(),
    routes: paths.map(path => ({ path, component: emptyPage })),
  })
  await router.push(options.path ?? '/words')
  await router.isReady()
  const i18n = createAppI18n()
  i18n.global.locale.value = options.locale ?? 'en'
  const wrapper = mount(AppNavigation, {
    props: { mobile: options.mobile ?? false },
    global: {
      plugins: [pinia, i18n, router],
    },
  })
  return {
    wrapper,
    cleanup() {
      wrapper.unmount()
      disposePinia(pinia)
    },
  }
}

describe('app navigation', () => {
  it('uses only start alignment on desktop and marks the active link for non-admin users', async () => {
    const { wrapper, cleanup } = await setup()
    try {
      const words = wrapper.get('a[href="/words"]')
      expect(words.classes()).toContain('justify-start')
      expect(words.classes()).not.toContain('justify-center')
      expect(words.get('span').classes()).toContain('text-left')
      expect(words.attributes('aria-current')).toBe('page')
      expect(words.classes()).toContain('bg-primary-soft')
      expect(wrapper.find('a[href="/admin/users"]').exists()).toBe(false)
      expect(wrapper.find('a[href="/admin/backup"]').exists()).toBe(false)
    }
    finally {
      cleanup()
    }
  })

  it('shows admin destinations only for admins and keeps localized sidebar labels left aligned', async () => {
    const { wrapper, cleanup } = await setup({ path: '/admin/users', role: 'admin', locale: 'zh-CN' })
    try {
      const users = wrapper.get('a[href="/admin/users"]')
      const backup = wrapper.get('a[href="/admin/backup"]')
      expect(users.text()).toContain('用户管理')
      expect(users.get('span').classes()).toEqual(expect.arrayContaining(['min-w-0', 'break-words', 'text-left']))
      expect(users.attributes('aria-current')).toBe('page')
      expect(backup.attributes('href')).toBe('/admin/backup')
      expect(backup.text()).toContain('备份')
    }
    finally {
      cleanup()
    }
  })

  it('keeps mobile destinations centered in columns with active state and without desktop admin links', async () => {
    const { wrapper, cleanup } = await setup({ path: '/review', mobile: true, role: 'admin' })
    try {
      const links = wrapper.findAll('a.navigation-link')
      expect(links.map(link => link.attributes('href'))).toEqual([
        '/projects',
        '/review',
        '/words',
        '/reading',
        '/settings',
      ])
      for (const link of links) {
        expect(link.classes()).toContain('justify-center')
        expect(link.classes()).not.toContain('justify-start')
        expect(link.classes()).toContain('flex-col')
      }
      const review = wrapper.get('a[href="/review"]')
      expect(review.attributes('aria-current')).toBe('page')
      expect(review.get('span').classes()).toContain('text-center')
      expect(review.get('.navigation-icon').classes()).toContain('shrink-0')
    }
    finally {
      cleanup()
    }
  })
})
