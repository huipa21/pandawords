import { flushPromises, mount } from '@vue/test-utils'
import { NSelect } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { createAppI18n } from '@/i18n'
import SenseRelations from './SenseRelations.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
const node = {
  id: 'target',
  table: 'sense',
  fields: { definition: 'Second meaning' },
}
const own = {
  id: 'own',
  start: 'sense',
  end: 'target',
  type: 'synonym',
  source: 'user',
  start_label: 'First meaning',
  end_label: 'Second meaning',
  readonly: false,
}
const shared = {
  ...own,
  id: 'source',
  readonly: true,
  source: 'dictionary',
}
function ok(data?: unknown) {
  return {
    data,
    response: new Response(),
  }
}
function fail(status = 500) {
  return {
    error: { code: 'private', message: 'SECRET' },
    response: new Response(null, { status }),
  }
}
let wrapper: ReturnType<typeof mount>
async function setup(locale: 'en' | 'zh-CN' = 'en') {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  wrapper = mount(SenseRelations, {
    props: { senseId: 'sense' },
    global: {
      plugins: [i18n],
    },
  })
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  client.GET.mockImplementation(async (path: string) => ok(path === '/api/relations'
    ? [shared]
    : [
        { ...node, id: 'sense' },
        node,
      ]))
  client.POST.mockResolvedValue(ok({ relation: own, created: true }))
  client.DELETE.mockResolvedValue(ok())
})
afterEach(() => {
  wrapper?.unmount()
  vi.resetAllMocks()
})
async function choose() {
  await wrapper.get('[data-testid="relation-search"]').trigger('click')
  await flushPromises()
  expect(client.GET).toHaveBeenLastCalledWith('/api/graph/seeds', {
    params: {
      query: {
        q: '',
        node_types: ['sense'],
        page: 1,
        page_size: 20,
      },
    },
  })
  expect(wrapper.findAll('[data-testid="relation-target"]')).toHaveLength(1)
  await wrapper.get('[data-testid="relation-target"]').trigger('click')
}

describe('personal semantic links', () => {
  it.each(['en', 'zh-CN'] as const)('validates explicit selection, creates and reports duplicate retries (%s)', async (locale) => {
    await setup(locale)
    expect(wrapper.find('[data-testid="relation-remove"]').exists()).toBe(false)
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(client.POST).not.toHaveBeenCalled()
    await choose()
    wrapper.findComponent(NSelect).vm.$emit('update:value', 'hypernym')
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/relations', {
      body: { start: 'sense', end: 'target', type: 'hypernym' },
    })
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.findAll('[role="status"]').map(item => item.text()).join(' ')).toContain(locale === 'en'
      ? 'Personal link created'
      : '已创建个人关联')
    client.POST.mockResolvedValueOnce(ok({ relation: own, created: false }))
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain(locale === 'en'
      ? 'already exists'
      : '已存在')
  })

  it('retains the selection after failed creation, retries, then confirms and retries removal', async () => {
    await setup()
    await choose()
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Your selection is kept')
    expect(wrapper.get('[data-testid="relation-target"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.emitted('changed')).toBeUndefined()
    client.GET.mockImplementation(async (path: string) => ok(path === '/api/relations'
      ? [shared, own]
      : [node]))
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    await flushPromises()
    expect(wrapper.findAll('[data-testid="relation-remove"]')).toHaveLength(1)
    await wrapper.get('[data-testid="relation-remove"]').trigger('click')
    expect(client.DELETE).not.toHaveBeenCalled()
    client.DELETE.mockResolvedValueOnce(fail())
    wrapper.findComponent(ConfirmAction).vm.$emit('confirm')
    await flushPromises()
    expect(wrapper.findComponent(ConfirmAction).props('show')).toBe(true)
    expect(wrapper.text()).not.toContain('SECRET')
    client.GET.mockResolvedValueOnce(ok([shared]))
    wrapper.findComponent(ConfirmAction).vm.$emit('confirm')
    await flushPromises()
    expect(client.DELETE).toHaveBeenLastCalledWith('/api/relations/{id}', {
      params: {
        path: { id: 'own' },
      },
    })
    expect(wrapper.find('[data-testid="relation-remove"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Personal link removed')
    expect(wrapper.emitted('changed')).toHaveLength(2)
  })

  it('recovers list/search/validation errors and ignores late responses after disposal', async () => {
    client.GET.mockResolvedValueOnce(fail())
    await setup()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    client.GET.mockResolvedValueOnce(fail())
    await wrapper.get('[data-testid="relation-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="relation-target"]').trigger('click')
    client.POST.mockResolvedValueOnce(fail(422))
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Check the selected senses')
    let resolve: (value: ReturnType<typeof ok>) => void = () => {}
    client.POST.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await wrapper.get('[data-testid="relation-create"]').trigger('click')
    wrapper.unmount()
    resolve(ok({ relation: own, created: true }))
    await flushPromises()
    expect(wrapper.emitted('changed')).toBeUndefined()
  })
})
