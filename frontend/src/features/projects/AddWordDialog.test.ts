import type { components } from '@/api/schema'
import { DOMWrapper, flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AddWordDialog from './AddWordDialog.vue'
import { button, failure, project, setup, success } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
let cleanup: (() => void) | undefined

function candidate(text = 'run', common = true): components['schemas']['Candidate'] {
  const lemmaId = ['en', text]
  const lexemeId = [...lemmaId, 'verb', 1]
  return {
    lemma: {
      id: lemmaId,
      text,
      lang: 'en',
      kind: 'word',
      freq_zipf: null,
      cefr: null,
      source: 'test',
    },
    matched_by: ['form'],
    lexemes: [
      {
        lexeme: {
          id: lexemeId,
          lemma_id: lemmaId,
          pos: 'verb',
          etymology_no: 1,
          etymology_text: null,
          source: 'test',
        },
        pronunciations: [],
        glosses: [],
        senses: ['move quickly', 'manage a business'].map((definition, rank) => ({
          id: [...lexemeId, `sense-${rank}`],
          lexeme_id: lexemeId,
          definition,
          glosses: [],
          gloss_zh: rank === 0
            ? '跑'
            : null,
          tags: [],
          register: [],
          domain: [],
          examples: [],
          rank,
          common: common && rank === 0,
          source: 'test',
          source_id: null,
          lexname: null,
        })),
      },
    ],
  }
}
const first = candidate()
const job: components['schemas']['JobRead'] = {
  id: 'job:enrich',
  type: 'enrich_dictionary',
  status: 'done',
  attempts: 1,
  run_after: '2026-11-14T00:00:00Z',
}
function receipt(jobs = [job]): components['schemas']['AddToProjectRead'] {
  return {
    project_id: project.id,
    lemma_id: 'lemma:run',
    lexeme_ids: ['lexeme:run'],
    selected_sense_ids: ['sense:run'],
    membership_ids: ['project_item:run'],
    jobs,
  }
}
function element(selector: string) {
  const found = document.body.querySelector(selector)
  if (!found)
    throw new Error(`Missing element ${selector}`)
  return new DOMWrapper(found)
}
async function open(locale: 'en' | 'zh-CN' = 'en') {
  const app = await setup(`/projects/${project.id}`, locale)
  cleanup = app.cleanup
  await app.wrapper.get('[data-testid="project-add-word"]').trigger('click')
  await flushPromises()
  return app
}
async function search() {
  await element('[data-testid="add-word-input"]').setValue('running')
  await element('[data-testid="add-word-search"]').trigger('click')
  await flushPromises()
}
beforeEach(() => {
  vi.resetAllMocks()
  client.GET.mockResolvedValue(success(project))
  client.POST.mockResolvedValue(success({
    normalized: 'running',
    candidates: [first],
    sources: [],
  }))
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('add word from a project', () => {
  it('selects common senses, submits explicit structured keys, locks duplicate submits, and safely repeats additions', async () => {
    const app = await open()
    await search()
    expect(client.POST).toHaveBeenCalledWith('/api/dictionary/candidates', {
      body: { text: 'running' },
      signal: expect.any(AbortSignal),
    })
    const common = element('[role="checkbox"][aria-label="move quickly"]')
    const rare = element('[role="checkbox"][aria-label="manage a business"]')
    expect(common.attributes('aria-checked')).toBe('true')
    expect(rare.attributes('aria-checked')).toBe('false')
    expect(document.body.textContent).toContain('跑')
    await common.trigger('click')
    expect(element('[data-testid="add-word-submit"]').attributes('disabled')).toBeDefined()
    await rare.trigger('click')
    let resolve!: (value: unknown) => void
    client.POST.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await element('[data-testid="add-word-submit"]').trigger('click')
    expect(element('[data-testid="add-word-submit"]').attributes('disabled')).toBeDefined()
    await element('[data-testid="add-word-submit"]').trigger('click')
    expect(client.POST).toHaveBeenCalledTimes(2)
    expect(client.POST).toHaveBeenLastCalledWith('/api/projects/{id}/dictionary', {
      params: {
        path: { id: project.id },
      },
      body: {
        lemma_key: first.lemma.id,
        selected_senses: [first.lexemes[0]!.senses[1]!.id],
      },
      signal: expect.any(AbortSignal),
    })
    resolve(success(receipt()))
    await flushPromises()
    expect(document.body.textContent).toContain('Adding again is safe')
    expect(element('[data-job-id="job:enrich"]').attributes('data-job-status')).toBe('done')
    client.POST.mockResolvedValueOnce(success(receipt([
      { ...job, status: 'queued' },
    ])))
    await element('[data-testid="add-word-submit"]').trigger('click')
    await flushPromises()
    expect(app.wrapper.findComponent(AddWordDialog).emitted('added')).toHaveLength(2)
    expect(app.wrapper.findComponent(AddWordDialog).emitted('jobsSettled')).toBeTruthy()
    expect(element('[data-job-id="job:enrich"]').attributes('data-job-status')).toBe('done')
    expect(document.body.querySelectorAll('[data-job-id="job:enrich"]')).toHaveLength(1)
    expect(client.GET).toHaveBeenCalledTimes(1)
    await element('[data-testid="add-word-close"]').trigger('click')
    await flushPromises()
    await app.wrapper.get('[data-testid="project-add-word"]').trigger('click')
    await flushPromises()
    expect(element('[data-job-id="job:enrich"]').attributes('data-job-status')).toBe('done')
    expect(client.GET).toHaveBeenCalledTimes(1)
  })

  it('shows candidate loading, no matches, localized recoverable search and add errors without losing selection', async () => {
    await open('zh-CN')
    let resolve!: (value: unknown) => void
    client.POST.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await search()
    expect(document.body.textContent).toContain('加载中')
    resolve(success({ normalized: 'running', candidates: [], sources: [] }))
    await flushPromises()
    expect(document.body.textContent).toContain('未找到匹配项')
    expect(document.body.querySelector('[data-testid="add-word-submit"]')).toBeNull()
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await element('[data-testid="add-word-search"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('无法连接服务器')
    client.POST.mockResolvedValueOnce(failure('auth.forbidden'))
    await element('[data-testid="add-word-search"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('你没有执行此操作的权限')
    client.POST.mockResolvedValueOnce(success({
      normalized: 'run',
      candidates: [first],
      sources: [],
    }))
    await element('[data-testid="add-word-search"]').trigger('click')
    await flushPromises()
    client.POST.mockResolvedValueOnce(failure('auth.forbidden'))
    await element('[data-testid="add-word-submit"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('你没有执行此操作的权限')
    expect(element('[role="checkbox"][aria-label="move quickly"]').attributes('aria-checked')).toBe('true')
    expect(element('[data-testid="add-word-submit"]').attributes('disabled')).toBeUndefined()
    client.POST.mockRejectedValueOnce(new Error('offline'))
    await element('[data-testid="add-word-submit"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('无法连接服务器')
    expect(document.body.textContent).not.toContain('NEVER DISPLAY')
    client.POST.mockResolvedValueOnce(success(receipt([])))
    await element('[data-testid="add-word-submit"]').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('已添加到此项目')
    expect(document.body.querySelector('[data-testid="job-status"]')).toBeNull()
  })

  it('switches candidates, requires a deliberate selection when none are common, and invalidates stale input/results', async () => {
    const second = candidate('runner', false)
    client.POST.mockResolvedValueOnce(success({
      normalized: 'running',
      candidates: [first, second],
      sources: [],
    }))
    await open()
    await search()
    await button('runner').trigger('click')
    await flushPromises()
    expect(element('[data-testid="add-word-submit"]').attributes('disabled')).toBeDefined()
    await element('[role="checkbox"][aria-label="manage a business"]').trigger('click')
    client.POST.mockResolvedValueOnce(success(receipt([])))
    await element('[data-testid="add-word-submit"]').trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenLastCalledWith('/api/projects/{id}/dictionary', expect.objectContaining({
      body: {
        lemma_key: second.lemma.id,
        selected_senses: [second.lexemes[0]!.senses[1]!.id],
      },
    }))
    await element('[data-testid="add-word-input"]').setValue('another')
    expect(document.body.querySelector('[data-testid="add-word-submit"]')).toBeNull()
    let resolve!: (value: unknown) => void
    client.POST.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await element('[data-testid="add-word-search"]').trigger('click')
    await element('[data-testid="add-word-close"]').trigger('click')
    const signal = client.POST.mock.calls.at(-1)![1].signal as AbortSignal
    expect(signal.aborted).toBe(true)
    resolve(success({
      normalized: 'another',
      candidates: [first],
      sources: [],
    }))
    await flushPromises()
    await element('[data-testid="project-add-word"]').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('[data-testid="add-word-submit"]')).toBeNull()
  })
})
