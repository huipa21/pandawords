import type { components } from '@/api/schema'
import { flushPromises, mount } from '@vue/test-utils'
import { NSelect } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createAppI18n } from '@/i18n'
import TagAssignments from './TagAssignments.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PUT: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
type Tag = components['schemas']['TagRead']
const own: Tag = {
  id: 'own',
  name: 'Travel',
  kind: 'custom',
  readonly: false,
}
const shared: Tag = {
  id: 'shared',
  name: 'Source',
  kind: 'domain',
  readonly: true,
}
const target = { target_table: 'sense', target_id: 'sense' } as const
function ok(data?: unknown) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
function fail() {
  return {
    error: { code: 'private', message: 'SECRET' },
    response: new Response(null, { status: 500 }),
  }
}
let cleanup: (() => void) | undefined

beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockImplementation(async (path: string) => path === '/api/tags'
    ? ok([shared])
    : ok([
        { tag: shared, readonly: true },
      ]))
  client.POST.mockResolvedValue(ok(own))
  client.PUT.mockResolvedValue(ok())
  client.DELETE.mockResolvedValue(ok())
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

async function setup(locale: 'en' | 'zh-CN' = 'en', wait = true) {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/tags',
        name: 'tags',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push('/tags')
  const wrapper = mount(TagAssignments, {
    props: { target },
    attachTo: document.body,
    global: {
      plugins: [i18n, router],
    },
  })
  cleanup = () => wrapper.unmount()
  if (wait)
    await flushPromises()
  return wrapper
}

describe('tag assignments', () => {
  it.each(['en', 'zh-CN'] as const)('creates, assigns, removes and restores with source memberships protected (%s)', async (locale) => {
    const wrapper = await setup(locale)
    expect(wrapper.find('[data-testid="tag-remove"]').exists()).toBe(false)
    await wrapper.get('[data-testid="tag-name"] input').setValue('Travel')
    await wrapper.get('[data-testid="tag-create"]').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/tags', {
      body: { name: 'Travel', kind: 'custom' },
    })
    await wrapper.get('[data-testid="tag-assign"]').trigger('click')
    await flushPromises()
    expect(client.PUT).toHaveBeenCalledWith('/api/tags/{id}/members', {
      params: {
        path: { id: 'own' },
      },
      body: target,
    })
    await wrapper.get('[data-testid="tag-remove"]').trigger('click')
    await flushPromises()
    expect(client.DELETE).toHaveBeenCalledWith('/api/tags/{id}/members', {
      params: {
        path: { id: 'own' },
        query: target,
      },
    })
    expect(wrapper.text()).toContain('Source')
    expect(wrapper.find('[data-testid="tag-remove"]').exists()).toBe(false)
    await wrapper.get('[data-testid="tag-undo"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="tag-remove"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tag-undo"]').exists()).toBe(false)
  })

  it('preserves create/assign/remove/undo state across recoverable failures without leaking server text', async () => {
    const wrapper = await setup()
    client.POST.mockResolvedValueOnce(fail())
    await wrapper.get('[data-testid="tag-name"] input').setValue('Travel')
    await wrapper.get('[data-testid="tag-create"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-testid="tag-name"] input').element as HTMLInputElement).value).toBe('Travel')
    expect(wrapper.text()).not.toContain('SECRET')
    await wrapper.get('[data-testid="tag-create"]').trigger('click')
    await flushPromises()
    client.PUT.mockResolvedValueOnce(fail())
    await wrapper.get('[data-testid="tag-assign"]').trigger('click')
    await flushPromises()
    expect(wrapper.findComponent(NSelect).props('value')).toBe('own')
    await wrapper.get('[data-testid="tag-assign"]').trigger('click')
    await flushPromises()
    client.DELETE.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="tag-remove"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="tag-remove"]').exists()).toBe(true)
    await wrapper.get('[data-testid="tag-remove"]').trigger('click')
    await flushPromises()
    client.PUT.mockResolvedValueOnce(fail())
    await wrapper.get('[data-testid="tag-undo"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="tag-undo"]').exists()).toBe(true)
    await wrapper.get('[data-testid="tag-undo"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="tag-remove"]').exists()).toBe(true)
    expect(client.POST).toHaveBeenCalledTimes(2)
  })

  it('shows loading, empty and retry states and rejects hierarchy cycles without losing selection', async () => {
    client.GET.mockResolvedValueOnce(fail())
    const wrapper = await setup('en', false)
    expect(wrapper.find('.n-skeleton').exists()).toBe(true)
    await flushPromises()
    expect(wrapper.text()).toContain('retry')
    client.GET.mockImplementation(async () => ok([]))
    const retry = wrapper.findAll('button').find(button => button.text() === 'Retry')!
    await retry.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('No tags yet.')
    await wrapper.get('[data-testid="tag-name"] input').setValue('Travel')
    await wrapper.get('[data-testid="tag-create"]').trigger('click')
    await flushPromises()
    client.PUT.mockResolvedValueOnce({
      error: { code: 'tag.cycle' },
      response: new Response(null, { status: 409 }),
    })
    await wrapper.get('[data-testid="tag-assign"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('cycle')
    expect(wrapper.findComponent(NSelect).props('value')).toBe('own')
  })
})
