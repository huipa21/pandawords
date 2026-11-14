import { flushPromises } from '@vue/test-utils'
import { NDatePicker, NInputNumber } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ErrorState from '@/components/app/ErrorState.vue'
import ProjectForm from '@/features/projects/ProjectForm.vue'
import { button, failure, plan, project, setup, success } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  PATCH: vi.fn(),
  PUT: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let cleanup: (() => void) | undefined

beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockImplementation((path: string) => Promise.resolve(success(
    path === '/api/projects/{id}/study-plan'
      ? plan
      : path === '/api/auth/me/srs-preferences'
        ? { desired_retention: 0.9 }
        : project,
  )))
  client.PATCH.mockImplementation((path: string) => Promise.resolve(success(
    path === '/api/auth/me/srs-preferences'
      ? { desired_retention: 0.85 }
      : project,
  )))
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('project study plan', () => {
  it('shows counts, seven UTC dates, past/impossible/buffer warnings and a scoped review link', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    const text = app.wrapper.text()
    expect(text).toContain('Remaining today: 16 new; 45 reviews.')
    expect(text).toContain('The exam time has passed')
    expect(text).toContain('cannot fit before the exam')
    expect(text).toContain('revision buffer is at risk')
    expect(app.wrapper.findAll('time')).toHaveLength(7)
    await button('Start review').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('project-review')
    expect(app.router.currentRoute.value.params.id).toBe(project.id)
  })

  it('preserves the full replacement plan and metadata; clears nullable values and accepts zero caps', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    const form = app.wrapper.getComponent(ProjectForm)
    await form.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH).toHaveBeenLastCalledWith('/api/projects/{id}', {
      params: {
        path: { id: project.id },
      },
      body: {
        name: project.name,
        description: project.description,
        source_lang: project.source_lang,
        target_lang: project.target_lang,
        plan: project.plan,
      },
    })
    form.findAllComponents(NInputNumber)[0]!.vm.$emit('update:value', 0)
    form.findAllComponents(NInputNumber)[1]!.vm.$emit('update:value', null)
    form.getComponent(NDatePicker).vm.$emit('update:value', null)
    await form.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH.mock.lastCall?.[1].body.plan).toEqual({ daily_new: 0, review_cap: null, exam_date: null })
    form.findAllComponents(NInputNumber)[1]!.vm.$emit('update:value', 0)
    await form.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH.mock.lastCall?.[1].body.plan.review_cap).toBe(0)
  })

  it('rejects invalid limits before saving and surfaces field/API/transport failures', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    const form = app.wrapper.getComponent(ProjectForm)
    form.findAllComponents(NInputNumber)[0]!.vm.$emit('update:value', -1)
    await form.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH).not.toHaveBeenCalled()
    form.findAllComponents(NInputNumber)[0]!.vm.$emit('update:value', 20)
    client.PATCH.mockResolvedValueOnce(failure('validation.invalid', 'plan.daily_new'))
    await form.get('form').trigger('submit')
    await flushPromises()
    expect(app.wrapper.text()).toContain('Check this value')
    expect(app.wrapper.text()).not.toContain('NEVER DISPLAY')
    client.PATCH.mockRejectedValueOnce(new Error('offline'))
    await form.get('form').trigger('submit')
    await flushPromises()
    expect(document.body.textContent).toContain('Cannot reach the server')
  })

  it('shows paused limits and an empty queue without enabling review', async () => {
    client.GET.mockImplementation((path: string) => Promise.resolve(success(
      path === '/api/projects/{id}/study-plan'
        ? {
            ...plan,
            plan: { daily_new: 0, review_cap: 0 },
            queue_total: 0,
            exam: null,
            remaining_new_allowance: 0,
            remaining_review_allowance: 0,
          }
        : path === '/api/auth/me/srs-preferences'
          ? { desired_retention: 0.9 }
          : project,
    )))
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    expect(app.wrapper.text()).toContain('A zero limit pauses that category')
    expect(app.wrapper.text()).toContain('No cards ready')
    expect(app.wrapper.text()).toContain('No exam date')
    expect(button('Start review').attributes('disabled')).toBeDefined()
  })

  it('keeps retention separate, validates bounds and does not send cards/history/project updates', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    const retention = app.wrapper.get('[data-testid="retention-form"]')
    const input = app.wrapper.findAllComponents(NInputNumber).at(-1)!
    for (const invalid of [
      null,
      0,
      1,
      -0.5,
      Number.POSITIVE_INFINITY,
    ]) {
      input.vm.$emit('update:value', invalid)
      await retention.trigger('submit')
      await flushPromises()
      expect(client.PATCH).not.toHaveBeenCalled()
    }
    input.vm.$emit('update:value', 0.85)
    await retention.trigger('submit')
    await flushPromises()
    expect(client.PATCH).toHaveBeenCalledExactlyOnceWith('/api/auth/me/srs-preferences', {
      body: { desired_retention: 0.85 },
    })
    expect(app.wrapper.text()).toContain('does not rewrite existing cards')
  })

  it('handles retention save failure without losing the edited value', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    client.PATCH.mockResolvedValueOnce(failure('auth.forbidden'))
    const input = app.wrapper.findAllComponents(NInputNumber).at(-1)!
    input.vm.$emit('update:value', 0.8)
    await app.wrapper.get('[data-testid="retention-form"]').trigger('submit')
    await flushPromises()
    expect(app.wrapper.text()).toContain('You do not have permission')
    expect(input.props('value')).toBe(0.8)
  })

  it('blocks duplicate personal preference submissions while the request is pending', async () => {
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    let resolve!: (value: ReturnType<typeof success>) => void
    client.PATCH.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    const form = app.wrapper.get('[data-testid="retention-form"]')
    await Promise.all([
      form.trigger('submit'),
      form.trigger('submit'),
    ])
    await flushPromises()
    expect(client.PATCH).toHaveBeenCalledTimes(1)
    expect(button('Save personal retention').attributes('disabled')).toBeDefined()
    resolve(success({ desired_retention: 0.9 }))
    await flushPromises()
    expect(button('Save personal retention').attributes('disabled')).toBeUndefined()
  })

  it('shows localized resource errors and retries without exposing server text', async () => {
    client.GET.mockResolvedValueOnce(failure('project.not_found', null, 404))
    const app = await setup(`/projects/${project.id}/plan`, 'zh-CN')
    cleanup = app.cleanup
    expect(app.wrapper.text()).not.toContain('NEVER DISPLAY')
    expect(app.wrapper.find('[data-testid="project-form"]').exists()).toBe(false)
    expect(app.wrapper.text()).not.toContain('study.')
    app.wrapper.getComponent(ErrorState).vm.$emit('retry')
    await flushPromises()
  })

  it('ignores a superseded project snapshot after navigating to another project', async () => {
    let resolve!: (value: ReturnType<typeof success>) => void
    client.GET.mockImplementation((path: string, options?: { params: { path: { id: string } } }) => {
      if (path === '/api/projects/{id}/study-plan') {
        return options?.params.path.id === project.id
          ? new Promise((done) => {
              resolve = done
            })
          : Promise.resolve(success({ ...plan, project_id: 'project:other', remaining_new_allowance: 77 }))
      }
      return Promise.resolve(success(path === '/api/auth/me/srs-preferences'
        ? { desired_retention: 0.9 }
        : { ...project, id: options?.params.path.id, name: options?.params.path.id }))
    })
    const app = await setup(`/projects/${project.id}/plan`)
    cleanup = app.cleanup
    await app.router.push('/projects/project:other/plan')
    await flushPromises()
    expect(app.wrapper.text()).toContain('Remaining today: 77 new')
    resolve(success(plan))
    await flushPromises()
    expect(app.wrapper.text()).toContain('Remaining today: 77 new')
    expect(app.wrapper.text()).not.toContain('Remaining today: 16 new')
  })
})
