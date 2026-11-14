import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { button, failure, plan, project, setup, success, tree } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  PATCH: vi.fn(),
  PUT: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let cleanup: (() => void) | undefined

beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockImplementation((path: string, options?: { params: { query: { page: number } } }) => {
    if (path === '/api/projects/{project_id}/tree') {
      return Promise.resolve(success({
        items: options?.params.query.page === 1
          ? [
              tree(['sense:a', 'sense:b']),
              tree(['sense:hidden'], true),
            ]
          : [
              tree(['sense:c']),
            ],
        total: 101,
        page: options?.params.query.page,
        page_size: 100,
      }))
    }
    return Promise.resolve(success(path === '/api/projects/{id}/study-plan'
      ? {
          ...plan,
          plan: { daily_new: 0, review_cap: 0 },
          queue: [],
          queue_total: 0,
        }
      : path === '/api/auth/me/srs-preferences'
        ? { desired_retention: 0.9 }
        : project))
  })
  client.PUT.mockResolvedValue(success({
    project_id: project.id,
    sense_ids: [
      'sense:b',
      'sense:hidden',
      'sense:a',
      'sense:c',
    ],
  }))
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('visible sense priority editor', () => {
  it('loads all tree pages, omits hidden ancestors and submits all visible senses even with a zero capped queue', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    await button('Prepare priority draft').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenCalledWith('/api/projects/{project_id}/tree', {
      params: {
        path: { project_id: project.id },
        query: { page: 2, page_size: 100, include_hidden: false },
      },
    })
    expect(app.wrapper.get('ol').text()).not.toContain('sense:hidden')
    expect(app.wrapper.get('ol').findAll('li')).toHaveLength(3)
    expect(button('Save priority').attributes('disabled')).toBeDefined()
    await app.wrapper.get('[aria-label="Move Definition sense:b up"]').trigger('click')
    await button('Save priority').trigger('click')
    await flushPromises()
    expect(client.PUT).toHaveBeenCalledExactlyOnceWith('/api/projects/{id}/study-plan/order', {
      params: {
        path: { id: project.id },
      },
      body: {
        sense_ids: ['sense:b', 'sense:a', 'sense:c'],
      },
    })
    expect(app.wrapper.get('ol').findAll('li')[0]!.text()).toContain('sense:b')
    expect(app.wrapper.get('ol').findAll('li')).toHaveLength(3)
    expect(app.wrapper.text()).toContain('Saved.')
  })

  it('disables save until the complete load succeeds and exposes retry after a later page error', async () => {
    let reads = 0
    const original = client.GET.getMockImplementation()!
    client.GET.mockImplementation((path, options) => {
      if (path === '/api/projects/{project_id}/tree' && ++reads === 2)
        return Promise.resolve(failure('study.invalid_order', null, 409))
      return original(path, options)
    })
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    await button('Prepare priority draft').trigger('click')
    await flushPromises()
    expect(app.wrapper.find('ol').exists()).toBe(false)
    expect(client.PUT).not.toHaveBeenCalled()
    expect(app.wrapper.text()).not.toContain('NEVER DISPLAY')
    await button('Retry').trigger('click')
    await flushPromises()
    expect(app.wrapper.get('ol').findAll('li')).toHaveLength(3)
  })

  it('retains the unsaved draft on a concurrent membership conflict and allows explicit reset', async () => {
    client.PUT.mockResolvedValueOnce(failure('study.invalid_order', null, 409))
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    await button('Prepare priority draft').trigger('click')
    await flushPromises()
    await app.wrapper.get('[aria-label="Move Definition sense:a down"]').trigger('click')
    await button('Save priority').trigger('click')
    await flushPromises()
    expect(app.wrapper.get('ol').findAll('li')[0]!.text()).toContain('sense:b')
    expect(app.wrapper.text()).toContain('The project selection changed')
    expect(button('Save priority').attributes('disabled')).toBeUndefined()
    await button('Reset draft to tree order').trigger('click')
    await flushPromises()
    expect(app.wrapper.get('ol').findAll('li')[0]!.text()).toContain('sense:a')
  })

  it('shows an empty state without offering an invalid reorder', async () => {
    const original = client.GET.getMockImplementation()!
    client.GET.mockImplementation((path, options) => path === '/api/projects/{project_id}/tree'
      ? Promise.resolve(success({
          items: [],
          total: 0,
          page: 1,
          page_size: 100,
        }))
      : original(path, options))
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    await button('Prepare priority draft').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('No visible selected senses')
    expect(app.wrapper.find('ol').exists()).toBe(false)
    expect(client.PUT).not.toHaveBeenCalled()
  })
})
