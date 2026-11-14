import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { createAppI18n } from '@/i18n'
import TagsPage from './TagsPage.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let cleanup: (() => void) | undefined
afterEach(() => cleanup?.())

it('keeps shared tags read-only and requires confirmation for owned deletion with safe retry', async () => {
  const shared = {
    id: 'shared',
    name: 'Source',
    kind: 'domain',
    readonly: true,
  }
  const own = {
    id: 'own',
    name: 'Travel',
    kind: 'custom',
    readonly: false,
  }
  client.GET.mockResolvedValue({
    data: [shared, own],
    response: new Response(null, { status: 200 }),
  })
  client.PATCH.mockResolvedValue({
    data: { ...own, name: 'Trips' },
    response: new Response(null, { status: 200 }),
  })
  client.DELETE.mockResolvedValueOnce({
    response: new Response(null, { status: 409 }),
  })
    .mockResolvedValueOnce({
      response: new Response(null, { status: 204 }),
    })
  const i18n = createAppI18n()
  i18n.global.locale.value = 'en'
  const wrapper = mount(TagsPage, {
    global: {
      plugins: [
        i18n,
      ],
    },
  })
  cleanup = () => wrapper.unmount()
  await flushPromises()
  const findButton = (text: string) => wrapper.findAll('button').find(button => button.text() === text)!
  expect(wrapper.findAll('button').filter(button => button.text() === 'Rename')).toHaveLength(1)
  await findButton('Rename').trigger('click')
  await wrapper.get('#tag-editor-name').setValue('Trips')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(wrapper.text()).toContain('Trips')
  await findButton('Delete tag').trigger('click')
  expect(client.DELETE).not.toHaveBeenCalled()
  wrapper.getComponent(ConfirmAction).vm.$emit('confirm')
  await flushPromises()
  expect(wrapper.text()).toContain('protected memberships')
  expect(wrapper.text()).toContain('Trips')
  wrapper.getComponent(ConfirmAction).vm.$emit('confirm')
  await flushPromises()
  expect(wrapper.text()).not.toContain('Trips')
  expect(wrapper.text()).toContain('Source')
})
