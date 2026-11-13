import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { nextTick } from 'vue'
import App from '@/App.vue'
import { createAppI18n } from '@/i18n'

describe('app', () => {
  it('renders the hello page in both languages and keeps metadata in sync', async () => {
    const i18n = createAppI18n()
    const wrapper = mount(App, {
      global: {
        plugins: [i18n],
      },
    })

    expect(wrapper.get('h1').text()).toBe('PandaWords')
    expect(wrapper.get('p').text()).toBe('前端已就绪。')
    expect(document.documentElement.lang).toBe('zh-CN')
    expect(document.title).toBe('PandaWords')

    i18n.global.locale.value = 'en'
    await nextTick()

    expect(wrapper.get('h1').text()).toBe('PandaWords')
    expect(wrapper.get('p').text()).toBe('Frontend is ready.')
    expect(document.documentElement.lang).toBe('en')
    expect(document.title).toBe('PandaWords')
    wrapper.unmount()
  })
})
