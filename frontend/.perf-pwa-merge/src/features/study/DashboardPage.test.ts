import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { button, dashboard, failure, setup, success } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let cleanup: (() => void) | undefined
beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockResolvedValue(success(dashboard))
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('review dashboard', () => {
  it('renders no-history, streak and project forecasts and navigates to the selected plan', async () => {
    const app = await setup()
    cleanup = app.cleanup
    expect(client.GET).toHaveBeenCalledWith('/api/dashboard')
    expect(app.wrapper.text()).toContain('No answers yet')
    expect(app.wrapper.text()).toContain('0 days')
    expect(app.wrapper.findAll('time')).toHaveLength(14)
    expect(app.wrapper.text()).not.toContain('NaN')
    await button('Study plan').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('project-plan')
    expect(app.router.currentRoute.value.params.id).toBe(dashboard.projects[0]!.project_id)
  })

  it('renders real zero retention as 0%, not no history, and retains history with no projects', async () => {
    client.GET.mockResolvedValue(success({ ...dashboard, retention_30_days: 0, projects: [] }))
    const app = await setup()
    cleanup = app.cleanup
    expect(app.wrapper.text()).toContain('0%')
    expect(app.wrapper.text()).not.toContain('No answers yet')
    expect(app.wrapper.text()).toContain('No projects to review')
    await button('Projects').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('projects')
  })

  it('handles transport failure, retries, and renders bilingual formatted retention', async () => {
    client.GET.mockRejectedValueOnce(new Error('private text'))
    const app = await setup('/review', 'zh-CN')
    cleanup = app.cleanup
    expect(app.wrapper.text()).not.toContain('private text')
    expect(app.wrapper.text()).not.toContain('study.')
    client.GET.mockResolvedValueOnce(success({ ...dashboard, retention_30_days: 0.875, streak: 4 }))
    await app.wrapper.get('[data-testid="study-dashboard"] button:last-child').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('87.5%')
    expect(app.wrapper.text()).toContain('4 天')
  })

  it('clears stale snapshots on refresh, shows loading, and localizes API errors', async () => {
    const app = await setup()
    cleanup = app.cleanup
    let resolve!: (value: ReturnType<typeof failure>) => void
    client.GET.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await button('Refresh').trigger('click')
    expect(app.wrapper.find('[role="status"]').exists()).toBe(true)
    expect(app.wrapper.text()).not.toContain('No answers yet')
    resolve(failure('auth.forbidden'))
    await flushPromises()
    expect(app.wrapper.text()).toContain('You do not have permission')
    expect(app.wrapper.text()).not.toContain('NEVER DISPLAY')
  })
})
