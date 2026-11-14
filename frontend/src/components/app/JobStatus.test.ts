import type { components } from '@/api/schema'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createAppI18n } from '@/i18n'
import JobStatus from './JobStatus.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
const job: components['schemas']['JobRead'] = {
  id: 'job:owned',
  type: 'enrich_dictionary',
  status: 'queued',
  attempts: 0,
  run_after: '2026-11-14T00:00:00Z',
}
function success(data: components['schemas']['JobRead']) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
function setup(jobs = [job], active = true) {
  const i18n = createAppI18n()
  i18n.global.locale.value = 'en'
  return mount(JobStatus, {
    props: { jobs, active },
    global: {
      plugins: [i18n],
    },
  })
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.useFakeTimers()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('owner-scoped background job progress', () => {
  it('polls queued/running jobs, retains both terminal states, and never polls them again', async () => {
    client.GET.mockResolvedValueOnce(success({ ...job, status: 'running' }))
      .mockResolvedValueOnce(success({ ...job, status: 'done' }))
    const failed = {
      ...job,
      id: 'job:failed',
      status: 'failed' as const,
      error: 'PRIVATE SERVER DETAIL',
    }
    const wrapper = setup([job, failed])
    await flushPromises()
    expect(client.GET).toHaveBeenCalledWith('/api/jobs/{id}', {
      params: {
        path: { id: job.id },
      },
      signal: expect.any(AbortSignal),
    })
    expect(wrapper.get('[data-job-id="job:owned"]').attributes('data-job-status')).toBe('running')
    expect(wrapper.text()).not.toContain('PRIVATE SERVER DETAIL')
    await vi.advanceTimersByTimeAsync(1500)
    await flushPromises()
    expect(wrapper.get('[data-job-id="job:owned"]').attributes('data-job-status')).toBe('done')
    expect(wrapper.get('[data-job-id="job:failed"]').attributes('data-job-status')).toBe('failed')
    expect(wrapper.emitted('settled')?.[0]?.[0]).toEqual([
      { ...job, status: 'done' },
      failed,
    ])
    await wrapper.setProps({ active: false })
    await wrapper.setProps({
      active: true,
      jobs: [
        job,
        { ...failed, status: 'queued' },
      ],
    })
    expect(wrapper.get('[data-job-id="job:owned"]').attributes('data-job-status')).toBe('done')
    expect(wrapper.get('[data-job-id="job:failed"]').attributes('data-job-status')).toBe('failed')
    await vi.advanceTimersByTimeAsync(4500)
    expect(client.GET).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('recovers from job API and transport failures without turning a queued job into a failed job', async () => {
    client.GET.mockResolvedValueOnce({
      error: { code: 'jobs.not_found', message: 'PRIVATE' },
      response: new Response(null, { status: 404 }),
    })
    const wrapper = setup()
    await flushPromises()
    expect(wrapper.text()).toContain('Could not check this job')
    expect(wrapper.get('[data-job-id="job:owned"]').attributes('data-job-status')).toBe('queued')
    await vi.advanceTimersByTimeAsync(3000)
    expect(client.GET).toHaveBeenCalledTimes(1)
    client.GET.mockRejectedValueOnce(new Error('offline'))
    await wrapper.get('[data-testid="job-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Could not check this job')
    client.GET.mockResolvedValueOnce(success({ ...job, status: 'failed', error: 'SECRET' }))
    await wrapper.get('[data-testid="job-retry"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Your word is still added')
    expect(wrapper.text()).not.toContain('SECRET')
    expect(wrapper.find('[data-testid="job-retry"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('aborts polling on close/unmount, ignores stale responses, and resumes pending jobs on reopen', async () => {
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    const wrapper = setup()
    const signal = client.GET.mock.calls[0]![1].signal as AbortSignal
    await wrapper.setProps({ active: false })
    expect(signal.aborted).toBe(true)
    resolve(success({ ...job, status: 'done' }))
    await flushPromises()
    expect(wrapper.get('[data-job-id="job:owned"]').attributes('data-job-status')).toBe('queued')
    await vi.advanceTimersByTimeAsync(4500)
    expect(client.GET).toHaveBeenCalledTimes(1)
    client.GET.mockResolvedValueOnce(success({ ...job, status: 'running' }))
    await wrapper.setProps({ active: true })
    await flushPromises()
    expect(client.GET).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-job-id="job:owned"]').attributes('data-job-status')).toBe('running')
    client.GET.mockReturnValueOnce(new Promise(() => {}))
    await vi.advanceTimersByTimeAsync(1500)
    const lastSignal = client.GET.mock.calls.at(-1)![1].signal as AbortSignal
    wrapper.unmount()
    expect(lastSignal.aborted).toBe(true)
    await vi.advanceTimersByTimeAsync(4500)
    expect(client.GET).toHaveBeenCalledTimes(3)
  })
})
