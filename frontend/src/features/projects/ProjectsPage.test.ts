import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { button, failure, list, project, setup, success } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let cleanup: (() => void) | undefined

beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockResolvedValue(list())
  client.DELETE.mockResolvedValue({
    response: new Response(null, { status: 204 }),
  })
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('project list', () => {
  it('shows loading, bilingual errors, retry, and an actionable empty state', async () => {
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    const app = await setup('/projects', 'zh-CN')
    cleanup = app.cleanup
    expect(app.wrapper.get('[role="status"]').attributes('aria-label')).toBe('加载中')
    resolve(failure('auth.forbidden'))
    await flushPromises()
    expect(app.wrapper.text()).toContain('你没有执行此操作的权限。')
    expect(app.wrapper.text()).not.toContain('NEVER DISPLAY')
    client.GET.mockResolvedValueOnce(list([]))
    await button('重试').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('暂无项目。')
    await app.wrapper.get('[data-testid="project-create"]').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('project-create')
  })

  it('keeps confirmed rows/page on failed pagination and retries the requested page', async () => {
    client.GET.mockResolvedValueOnce(list([project], 1, 21))
    const app = await setup()
    cleanup = app.cleanup
    client.GET.mockRejectedValueOnce(new Error('offline'))
    await button('Next').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('Page 1 of 2')
    expect(app.wrapper.text()).toContain(project.name)
    expect(app.wrapper.text()).toContain('Cannot reach the server.')
    client.GET.mockResolvedValueOnce(list([
      { ...project, id: 'project:second', name: 'Second' },
    ], 2, 21))
    await button('Retry').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/projects', {
      params: {
        query: { page: 2, page_size: 20 },
      },
    })
    expect(app.wrapper.text()).toContain('Page 2 of 2')
    expect(button('Next').attributes('disabled')).toBeDefined()
  })

  it('confirms deletion, permits cancellation, handles errors, and accepts an empty 204 response', async () => {
    const app = await setup()
    cleanup = app.cleanup
    await app.wrapper.get('[data-testid="project-delete"]').trigger('click')
    await flushPromises()
    expect(client.DELETE).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain(`Permanently delete ${project.name}`)
    await button('Cancel').trigger('click')
    await flushPromises()
    expect(client.DELETE).not.toHaveBeenCalled()
    await app.wrapper.get('[data-testid="project-delete"]').trigger('click')
    await flushPromises()
    client.DELETE.mockResolvedValueOnce(failure('project.membership_conflict', null, 409))
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('memberships are inconsistent')
    expect(app.wrapper.findComponent(ConfirmAction).props('show')).toBe(true)
    client.DELETE.mockRejectedValueOnce(new Error('offline'))
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Cannot reach the server.')
    client.GET.mockResolvedValueOnce(list([]))
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(client.DELETE).toHaveBeenLastCalledWith('/api/projects/{id}', {
      params: {
        path: { id: project.id },
      },
    })
    expect(app.wrapper.text()).toContain('No projects yet.')
    expect(app.wrapper.findComponent(ConfirmAction).props('show')).toBe(false)
  })

  it('moves to the preceding page after deleting the final card', async () => {
    client.GET.mockResolvedValueOnce(list([project], 2, 21))
    const app = await setup()
    cleanup = app.cleanup
    await app.wrapper.get('[data-testid="project-delete"]').trigger('click')
    await flushPromises()
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/projects', {
      params: {
        query: { page: 1, page_size: 20 },
      },
    })
  })

  it('opens the project detail shell without fetching a speculative tree', async () => {
    const app = await setup()
    cleanup = app.cleanup
    client.GET.mockResolvedValueOnce(success(project))
    await app.wrapper.get('[data-testid="project-card"] a').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.params.id).toBe(project.id)
    expect(app.wrapper.text()).toContain('The project is ready.')
    expect(client.GET).toHaveBeenLastCalledWith('/api/projects/{id}', {
      params: {
        path: { id: project.id },
      },
    })
    expect(client.GET).toHaveBeenCalledTimes(2)
    client.GET.mockResolvedValueOnce(success(project))
    await app.wrapper.get('[data-testid="project-edit"]').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('project-edit')
    expect(app.wrapper.get<HTMLInputElement>('#project-name').element.value).toBe(project.name)
  })

  it('does not resurrect a deleted card when the following refresh fails', async () => {
    const app = await setup()
    cleanup = app.cleanup
    await app.wrapper.get('[data-testid="project-delete"]').trigger('click')
    await flushPromises()
    client.GET.mockRejectedValueOnce(new Error('offline'))
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(app.wrapper.find('[data-testid="project-card"]').exists()).toBe(false)
    expect(app.wrapper.text()).toContain('Cannot reach the server.')
    client.GET.mockResolvedValueOnce(list([]))
    await button('Retry').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('No projects yet.')
  })
})
