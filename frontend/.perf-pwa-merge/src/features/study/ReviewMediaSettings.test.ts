import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NRadioGroup, NSwitch } from 'naive-ui'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createAppI18n } from '@/i18n'
import ReviewMediaSettings from './ReviewMediaSettings.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  PATCH: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
const defaults = { review_images_enabled: true, review_audio_enabled: true, accent: 'US' }
function ok(data: unknown) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
let cleanup: (() => void) | undefined
beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockResolvedValue(ok(defaults))
  client.PATCH.mockImplementation(async (_path, { body }) => ok(body))
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

it.each(['en', 'zh-CN'] as const)('loads and saves both toggles and accent with accessible localized controls in %s', async (locale) => {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(defineComponent({
    setup: () => () => h(NConfigProvider, null, {
      default: () => h(ReviewMediaSettings),
    }),
  }), {
    global: {
      plugins: [i18n],
    },
    attachTo: document.body,
  })
  cleanup = () => wrapper.unmount()
  await flushPromises()
  const switches = wrapper.findAllComponents(NSwitch)
  expect(switches.map(item => item.props('value'))).toEqual([true, true])
  expect(wrapper.findAll('[role="switch"]').every(item => item.attributes('aria-label'))).toBe(true)
  switches[0]!.vm.$emit('update:value', false)
  switches[1]!.vm.$emit('update:value', false)
  wrapper.findComponent(NRadioGroup).vm.$emit('update:value', 'UK')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(client.PATCH).toHaveBeenLastCalledWith('/api/auth/me/review-preferences', {
    body: { review_images_enabled: false, review_audio_enabled: false, accent: 'UK' },
  })
  expect(wrapper.text()).toContain(locale === 'en'
    ? 'Saved'
    : '已保存')
  switches[0]!.vm.$emit('update:value', true)
  switches[1]!.vm.$emit('update:value', true)
  client.PATCH.mockRejectedValueOnce(new Error('offline'))
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(true)
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(client.PATCH).toHaveBeenLastCalledWith('/api/auth/me/review-preferences', {
    body: { ...defaults, accent: 'UK' },
  })
})
