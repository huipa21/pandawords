import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import App from '@/App.vue'

describe('app', () => {
  it('renders the hello page', () => {
    const wrapper = mount(App)

    expect(wrapper.get('h1').text()).toBe('PandaWords')
    expect(wrapper.text()).toContain('Frontend is ready.')
  })
})
