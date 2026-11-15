import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createAppI18n } from '@/i18n'
import AppShell from './AppShell.vue'

describe('app shell', () => {
  it('renders the header above stretched white panels and reserves the mobile navigation area', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        {
          path: '/',
          component: defineComponent({
            render: () => h('div', { 'data-testid': 'route-content' }),
          }),
        },
      ],
    })
    await router.push('/')
    await router.isReady()
    const wrapper = mount(AppShell, {
      global: {
        plugins: [
          createAppI18n(),
          router,
        ],
        stubs: {
          AppHeader: { template: '<header data-testid="shell-header" />' },
          AppNavigation: { template: '<nav data-testid="shell-navigation" />' },
        },
      },
    })
    try {
      const root = wrapper.element
      expect(root.classList.contains('p-4')).toBe(true)
      expect(root.classList.contains('lg:p-6')).toBe(true)
      expect(root.classList.contains('gap-4')).toBe(true)
      expect(root.classList.contains('bg-page')).toBe(true)
      expect(root.children[1]).toBe(wrapper.get('[data-testid="shell-header"]').element)

      const body = wrapper.findAll('div').find(element => element.classes().includes('items-stretch'))
      expect(body?.classes()).toEqual(expect.arrayContaining([
        'flex',
        'flex-1',
        'items-stretch',
        'gap-4',
      ]))

      const sidebar = wrapper.get('aside')
      const main = wrapper.get('main')
      for (const panel of [sidebar, main]) {
        expect(panel.classes()).toEqual(expect.arrayContaining([
          'rounded-lg',
          'border',
          'border-base',
          'bg-surface',
          'shadow-1',
        ]))
      }
      expect(sidebar.classes()).toEqual(expect.arrayContaining(['w-sidebar', 'shrink-0', 'lg:block']))
      expect(sidebar.classes()).toContain('hidden')
      expect(main.attributes('id')).toBe('main-content')
      expect(main.attributes('tabindex')).toBe('-1')
      expect(main.find('.max-w-content [data-testid="route-content"]').exists()).toBe(true)
      expect(wrapper.get('.bottom-navigation').classes()).toContain('lg:hidden')
      expect(root.classList.contains('pb-bottom-nav')).toBe(true)
      expect(root.classList.contains('lg:pb-0')).toBe(true)
    }
    finally {
      wrapper.unmount()
    }
  })
})
