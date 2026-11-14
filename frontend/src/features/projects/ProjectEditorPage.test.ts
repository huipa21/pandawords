import { flushPromises } from '@vue/test-utils'
import { NDatePicker, NInputNumber } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
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
  client.GET.mockResolvedValue(success(project))
  client.POST.mockResolvedValue(success(project))
  client.PATCH.mockResolvedValue(success(project))
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('project editor', () => {
  it('validates required/maximum text lengths and non-negative safe integers before creating', async () => {
    const app = await setup('/projects/new')
    cleanup = app.cleanup
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.POST).not.toHaveBeenCalled()
    expect(app.wrapper.text()).toContain('Enter 1–128 characters')
    for (const [id, value] of [
      [
        'name',
        'x'.repeat(129),
      ],
      [
        'description',
        'x'.repeat(10001),
      ],
      ['target_lang', ' '],
      [
        'source_lang',
        'x'.repeat(36),
      ],
    ]) {
      await app.wrapper.get(`#project-${id}`).setValue(value)
    }
    const numbers = app.wrapper.findAllComponents(NInputNumber)
    numbers[0]!.vm.$emit('update:value', -1)
    numbers[1]!.vm.$emit('update:value', 1.5)
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.POST).not.toHaveBeenCalled()
    expect(app.wrapper.text()).toContain('Use at most 10,000 characters.')
    expect(app.wrapper.text()).toContain('Enter a non-negative whole number')
    numbers[0]!.vm.$emit('update:value', Number.MAX_SAFE_INTEGER + 1)
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.POST).not.toHaveBeenCalled()
    numbers[0]!.vm.$emit('update:value', null)
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.POST).not.toHaveBeenCalled()
  })

  it('creates with trimmed inputs and contract defaults, blocks double submission and navigates to detail', async () => {
    let resolve!: (value: unknown) => void
    client.POST.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    const app = await setup('/projects/new')
    cleanup = app.cleanup
    expect(client.GET).not.toHaveBeenCalled()
    expect(app.wrapper.get('#project-exam-date input').element.closest('label')?.textContent).toContain('Exam date (optional)')
    await app.wrapper.get('#project-name').setValue('  My project  ')
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/projects', {
      body: {
        name: 'My project',
        description: '',
        target_lang: 'en',
        source_lang: 'zh',
        plan: { daily_new: 20, review_cap: null, exam_date: null },
      },
    })
    expect(app.wrapper.get('#project-name').attributes('disabled')).toBeDefined()
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledTimes(1)
    resolve(success(project))
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('project')
    expect(app.router.currentRoute.value.params.id).toBe(project.id)
  })

  it('preserves the full existing plan on edit and clears nullable settings explicitly', async () => {
    const app = await setup('/projects/project:sample/edit')
    cleanup = app.cleanup
    await app.wrapper.get('#project-name').setValue('Updated')
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH).toHaveBeenCalledWith('/api/projects/{id}', {
      params: {
        path: { id: project.id },
      },
      body: {
        name: 'Updated',
        description: project.description,
        target_lang: 'en',
        source_lang: 'zh',
        plan: project.plan,
      },
    })
    await app.router.push('/projects/project:sample/edit')
    await flushPromises()
    app.wrapper.findAllComponents(NInputNumber)[1]!.vm.$emit('update:value', null)
    app.wrapper.findComponent(NDatePicker).vm.$emit('update:value', null)
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(client.PATCH.mock.calls.at(-1)![1].body.plan).toEqual({ daily_new: 20, review_cap: null, exam_date: null })
  })

  it('maps server field, unknown and transport errors without exposing raw messages', async () => {
    const app = await setup('/projects/new', 'zh-CN')
    cleanup = app.cleanup
    await app.wrapper.get('#project-name').setValue('My project')
    client.POST.mockResolvedValueOnce(failure('validation.invalid', 'name', 422))
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(app.wrapper.text()).toContain('请检查此项后重试。')
    expect(app.router.currentRoute.value.name).toBe('project-create')
    client.POST.mockResolvedValueOnce(failure('private.unknown'))
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(document.body.textContent).toContain('请求失败，请重试。')
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await app.wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(document.body.textContent).toContain('无法连接服务器')
    expect(document.body.textContent).not.toContain('NEVER DISPLAY')
  })

  it('shows unavailable edit/detail states for owner-filtered 404s and retries', async () => {
    client.GET.mockResolvedValueOnce(failure('project.not_found', null, 404))
    const app = await setup('/projects/project:other/edit')
    cleanup = app.cleanup
    expect(app.wrapper.text()).toContain('This project is unavailable or no longer exists.')
    expect(app.wrapper.find('form').exists()).toBe(false)
    await button('Retry').trigger('click')
    await flushPromises()
    expect(app.wrapper.find('form').exists()).toBe(true)
    client.GET.mockResolvedValueOnce(failure('project.not_found', null, 404))
    await app.router.push('/projects/project:other')
    await flushPromises()
    expect(app.wrapper.text()).toContain('This project is unavailable or no longer exists.')
    expect(app.wrapper.text()).not.toContain('The project is ready.')
  })

  it('cancels without saving and ignores an obsolete response when the route changes', async () => {
    let resolve!: (value: unknown) => void
    const app = await setup('/projects/project:sample/edit')
    cleanup = app.cleanup
    client.GET.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await app.router.push('/projects/project:slow/edit')
    await flushPromises()
    expect(app.wrapper.find('[role="status"]').exists()).toBe(true)
    await app.router.push('/projects/new')
    await flushPromises()
    expect(app.wrapper.find('form').exists()).toBe(true)
    expect(app.wrapper.get<HTMLInputElement>('#project-name').element.value).toBe('')
    resolve(success(project))
    await flushPromises()
    expect(app.wrapper.get<HTMLInputElement>('#project-name').element.value).toBe('')
    client.GET.mockResolvedValueOnce(list([]))
    await button('Cancel').trigger('click')
    await flushPromises()
    expect(app.router.currentRoute.value.name).toBe('projects')
    expect(client.POST).not.toHaveBeenCalled()
    expect(client.PATCH).not.toHaveBeenCalled()
  })
})
