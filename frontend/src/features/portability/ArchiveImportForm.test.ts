import type { ImportSummary, RestoreSummary } from './requests'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import ArchiveImportForm from './ArchiveImportForm.vue'
import { abortable, apiError, archive, chooseFile, clickText, mountPage, query } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}))
vi.mock('@/api/client', async original => ({
  ...await original<typeof import('@/api/client')>(),
  api: client,
}))

const imported: ImportSummary = {
  project_ids: ['project:copy'],
  progress_imported: true,
  same_source: true,
  created: { lemma: 2, sense: 3 },
  merged: { lemma: 1 },
  skipped: {},
  conflicts: [],
  warnings: ['1 image skipped'],
}
const restored: RestoreSummary = {
  ...imported,
  already_restored: false,
  preferences_restored: ['theme'],
  preferences_kept: ['locale'],
}

function ok(data: unknown) {
  return {
    data,
    response: new Response(null, { status: 201 }),
  }
}

let cleanup: (() => void) | undefined
async function setup(kind: 'project' | 'user', locale: 'en' | 'zh-CN' = 'en') {
  const page = defineComponent({
    setup: () => () => h(ArchiveImportForm, { kind }),
  })
  const mounted = await mountPage(page, locale)
  cleanup = mounted.cleanup
  return mounted
}
const text = () => document.body.textContent ?? ''
async function submit() {
  query('[data-testid="archive-submit"]').click()
  await flushPromises()
}
const lastQuery = () => client.POST.mock.lastCall![1].params.query

async function pickProgress(option: 'auto' | 'on' | 'off') {
  query(`[data-testid="progress-${option}"] input`).click()
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  client.POST.mockResolvedValue(ok(imported))
})
afterEach(() => {
  cleanup?.()
  cleanup = undefined
  document.body.innerHTML = ''
})

describe('project import', () => {
  it('rejects wrong extension, empty and oversized files before uploading', async () => {
    await setup('project')
    expect(query('[data-testid="archive-file"]').textContent).toContain('No archive selected.')
    expect(query('[data-testid="archive-submit"]').hasAttribute('disabled')).toBe(true)
    await chooseFile(archive('notes.zip'))
    expect(text()).toContain('Choose a .tar.gz archive exported by PandaWords.')
    await chooseFile(archive('deck.tgz', 0))
    expect(text()).toContain('This file is empty.')
    const huge = archive()
    Object.defineProperty(huge, 'size', { value: 600 * 1024 * 1024 })
    await chooseFile(huge)
    expect(text()).toContain('larger than the 512.0 MB upload limit')
    expect(query('[data-testid="archive-submit"]').hasAttribute('disabled')).toBe(true)
    expect(client.POST).not.toHaveBeenCalled()
  })

  it('imports a valid archive with the chosen progress option as a query parameter', async () => {
    const { wrapper, router } = await setup('project')
    const file = archive()
    await chooseFile(file)
    expect(text()).toContain('deck.pandawords-project.tar.gz (4 B)')
    expect(query('[data-testid="progress-hint"]').textContent).toContain('exported by your own account')
    await submit()
    expect(client.POST).toHaveBeenLastCalledWith('/api/projects/import', expect.objectContaining({
      params: { query: {} },
      body: file,
      headers: { 'Content-Type': 'application/gzip' },
      signal: expect.any(AbortSignal),
    }))
    expect(query('[data-testid="archive-summary"]').textContent).toContain('Project imported.')
    expect(text()).toContain('Learning progress was imported.')
    expect(text()).toContain('1 project(s) added.')
    expect(text()).toContain('1 notice(s)')
    expect(wrapper.findComponent(ArchiveImportForm).emitted('done')).toEqual([
      [imported],
    ])

    for (const [option, value] of [
      ['on', true],
      ['off', false],
    ] as const) {
      await pickProgress(option)
      await chooseFile(file)
      await submit()
      expect(lastQuery()).toEqual({ include_progress: value })
    }
    expect(query('[data-testid="progress-hint"]').textContent).toContain('Every word becomes a new card')
    query('[data-testid="archive-open-project"]').click()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/projects/project:copy')
  })

  it.each([
    [
      422,
      'bundle.integrity',
      'references',
      'failed its integrity check',
      'Failed at: references',
    ],
    [
      409,
      'bundle.identity_conflict',
      'apply',
      'belongs to another account',
      'Failed at: saving',
    ],
    [
      413,
      'bundle.too_large',
      'upload',
      'exceeds the server upload limit',
      'Failed at: upload',
    ],
    [
      422,
      'bundle.dangling_reference',
      'data',
      'archive was rejected',
      'Failed at: data',
    ],
  ])('shows a localized %i %s rejection with its stage and keeps the file for retry', async (status, code, stage, message, failed) => {
    await setup('project')
    await chooseFile(archive())
    await pickProgress('off')
    client.POST.mockResolvedValueOnce(apiError(code, status, {
      stage,
      problems: ['sense 3 has no lexeme'],
    }))
    await submit()
    const error = query('[data-testid="archive-error"]').textContent
    expect(error).toContain(message)
    expect(error).toContain(failed)
    expect(error).toContain('sense 3 has no lexeme')
    expect(text()).not.toContain('NEVER DISPLAY')
    expect(text()).toContain('deck.pandawords-project.tar.gz')
    await submit()
    expect(client.POST).toHaveBeenCalledTimes(2)
    expect(client.POST.mock.calls[1]![1]).toMatchObject({ body: client.POST.mock.calls[0]![1].body })
    expect(lastQuery()).toEqual({ include_progress: false })
    expect(query('[data-testid="archive-summary"]')).toBeTruthy()
  })

  it('reports transport failures and stays retryable', async () => {
    await setup('project')
    await chooseFile(archive())
    client.POST.mockRejectedValueOnce(new TypeError('offline'))
    await submit()
    expect(query('[data-testid="archive-error"]').textContent).toContain('Cannot reach the server.')
    expect(query('[data-testid="archive-submit"]').textContent).toContain('Retry')
  })

  it('shows bounded status while uploading and cancels with an AbortController', async () => {
    await setup('project')
    await chooseFile(archive())
    await pickProgress('on')
    client.POST.mockImplementationOnce(abortable())
    await submit()
    expect(query('[data-testid="archive-status"]').textContent).toContain('Uploading and validating 4 B')
    expect(query('[data-testid="archive-input"]').hasAttribute('disabled')).toBe(true)
    const signal: AbortSignal = client.POST.mock.lastCall![1].signal
    query('[data-testid="archive-cancel"]').click()
    await flushPromises()
    expect(signal.aborted).toBe(true)
    expect(query('[data-testid="archive-status"]').textContent).toContain('Upload cancelled.')
    expect(document.body.querySelector('[data-testid="archive-error"]')).toBeNull()
    await submit()
    expect(lastQuery()).toEqual({ include_progress: true })
    expect(query('[data-testid="archive-summary"]')).toBeTruthy()
  })

  it('renders localized zh-CN states', async () => {
    await setup('project', 'zh-CN')
    expect(text()).not.toContain('No archive selected.')
    await chooseFile(archive())
    client.POST.mockResolvedValueOnce(apiError('bundle.integrity', 422, { stage: 'media', problems: [] }))
    await clickText('导入')
    expect(query('[data-testid="archive-error"]').textContent).not.toMatch(/[A-Z]{4,}/i)
    await clickText('重试')
    expect(query('[data-testid="archive-summary"]').textContent).not.toContain('Project imported.')
  })
})

describe('user restore', () => {
  it('explains the merge before restoring, defaults progress on, and targets only the current user', async () => {
    client.POST.mockResolvedValue(ok(restored))
    await setup('user')
    await chooseFile(archive('me.pandawords-user.tar.gz'))
    await clickText('Restore')
    expect(client.POST).not.toHaveBeenCalled()
    expect(text()).toContain('Restore me.pandawords-user.tar.gz into your account?')
    await clickText('Cancel')
    expect(client.POST).not.toHaveBeenCalled()
    await clickText('Restore')
    await clickText('Confirm')
    expect(client.POST).toHaveBeenCalledTimes(1)
    expect(client.POST).toHaveBeenLastCalledWith('/api/me/restore', expect.objectContaining({
      params: {
        query: { include_progress: true },
      },
    }))
    expect(JSON.stringify(client.POST.mock.lastCall)).not.toMatch(/user:|owner|user_id/)
    expect(text()).toContain('Backup restored.')
    expect(text()).toContain('Preferences restored: theme')
    expect(text()).toContain('Preferences kept (you had changed them): locale')
    expect(document.body.querySelector('[data-testid="archive-open-project"]')).toBeNull()
  })

  it('offers only on/off progress and reports an already-restored backup', async () => {
    client.POST.mockResolvedValue(ok({ ...restored, already_restored: true }))
    await setup('user')
    expect(document.body.querySelector('[data-testid="progress-auto"]')).toBeNull()
    await chooseFile(archive('me.pandawords-user.tar.gz'))
    await pickProgress('off')
    await clickText('Restore')
    await clickText('Confirm')
    expect(lastQuery()).toEqual({ include_progress: false })
    expect(text()).toContain('This backup was already restored; nothing was changed.')
  })
})
