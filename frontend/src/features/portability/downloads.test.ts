import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import ProjectExportButton from './ProjectExportButton.vue'
import { abortable, apiError, blobResult, captureDownloads, mountPage, query } from './testHarness'
import UserBackupSection from './UserBackupSection.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}))
vi.mock('@/api/client', async original => ({
  ...await original<typeof import('@/api/client')>(),
  api: client,
}))

let cleanup: (() => void) | undefined
let saved: string[]
async function setup(kind: 'project' | 'user', locale: 'en' | 'zh-CN' = 'en') {
  const page = defineComponent({
    setup: () => () => kind === 'project'
      ? h(ProjectExportButton, { projectId: 'project:mine' })
      : h(UserBackupSection),
  })
  const mounted = await mountPage(page, locale)
  cleanup = mounted.cleanup
}
const text = () => document.body.textContent ?? ''
async function click(selector: string) {
  query(selector).click()
  await flushPromises()
}

beforeEach(() => {
  vi.clearAllMocks()
  saved = captureDownloads()
})
afterEach(() => {
  cleanup?.()
  cleanup = undefined
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('project export', () => {
  it('downloads the owned project archive under a safe file name without exposing a URL', async () => {
    client.GET.mockResolvedValueOnce(blobResult('../../secret/deck.pandawords-project.tar.gz', { 'X-PandaWords-Skipped-Media': '2' }))
    await setup('project')
    await click('[data-testid="project-export"]')
    expect(client.GET).toHaveBeenCalledWith('/api/projects/{id}/export', {
      params: {
        path: { id: 'project:mine' },
      },
      parseAs: 'blob',
      signal: expect.any(AbortSignal),
    })
    expect(saved).toEqual(['deck.pandawords-project.tar.gz'])
    expect(text()).toContain('Project archive downloaded.')
    expect(text()).toContain('2 media file(s) could not be included.')
    expect(text()).not.toMatch(/blob:|secret|\/api\//)
  })

  it('shows a localized failure and allows another attempt', async () => {
    client.GET.mockResolvedValueOnce(apiError('project.not_found', 404))
    await setup('project', 'zh-CN')
    await click('[data-testid="project-export"]')
    expect(saved).toEqual([])
    expect(text()).toContain('此项目不可用或已不存在。')
    expect(text()).not.toContain('NEVER DISPLAY')
    expect(query('[data-testid="project-export"]').hasAttribute('disabled')).toBe(false)
  })

  it('cancels an in-flight export', async () => {
    client.GET.mockImplementationOnce(abortable())
    await setup('project')
    query('[data-testid="project-export"]').click()
    await flushPromises()
    expect(query('[data-testid="project-export"]').textContent).toContain('Preparing…')
    const signal: AbortSignal = client.GET.mock.lastCall![1].signal
    await click('[data-testid="project-export-cancel"]')
    expect(signal.aborted).toBe(true)
    expect(document.body.querySelector('[data-testid="project-export-cancel"]')).toBeNull()
    expect(query('[data-testid="project-export"]').textContent).toContain('Export')
    expect(saved).toEqual([])
    expect(text()).not.toContain('Cannot reach the server.')
  })
})

describe('user backup', () => {
  it('downloads only the current user backup and reports the saved file', async () => {
    client.GET.mockResolvedValueOnce({
      data: new Blob(['archive']),
      response: new Response(null, { status: 200 }),
    })
    await setup('user')
    await click('[data-testid="user-backup-download"]')
    expect(client.GET).toHaveBeenCalledTimes(1)
    expect(client.GET).toHaveBeenCalledWith('/api/me/backup', {
      parseAs: 'blob',
      signal: expect.any(AbortSignal),
    })
    expect(saved).toEqual(['pandawords-backup.pandawords-user.tar.gz'])
    expect(query('[data-testid="user-backup-status"]').textContent).toContain('Saved pandawords-backup.pandawords-user.tar.gz.')
    expect(client.POST).not.toHaveBeenCalled()
  })

  it('shows localized size-limit and transport errors that can be retried', async () => {
    client.GET.mockResolvedValueOnce(apiError('backup.export_too_large', 413))
    await setup('user', 'zh-CN')
    expect(query('[data-testid="archive-file"]').textContent).not.toMatch(/[A-Z]{4,}/i)
    await click('[data-testid="user-backup-download"]')
    const error = query('[data-testid="user-backup-error"]').textContent
    expect(error).toContain('你的数据超过备份大小上限')
    expect(error).not.toMatch(/[A-Z]{4,}/i)
    client.GET.mockRejectedValueOnce(new TypeError('offline'))
    await click('[data-testid="user-backup-download"]')
    expect(query('[data-testid="user-backup-error"]').textContent).toContain('无法连接服务器')
    client.GET.mockResolvedValueOnce(blobResult('me.pandawords-user.tar.gz', { 'X-PandaWords-Skipped-Media': '1' }))
    await click('[data-testid="user-backup-download"]')
    expect(document.body.querySelector('[data-testid="user-backup-error"]')).toBeNull()
    expect(saved).toEqual(['me.pandawords-user.tar.gz'])
  })

  it('cancels a running backup download', async () => {
    client.GET.mockImplementationOnce(abortable())
    await setup('user')
    await click('[data-testid="user-backup-download"]')
    const signal: AbortSignal = client.GET.mock.lastCall![1].signal
    await click('[data-testid="user-backup-cancel"]')
    expect(signal.aborted).toBe(true)
    expect(document.body.querySelector('[data-testid="user-backup-error"]')).toBeNull()
    expect(query('[data-testid="user-backup-status"]').textContent?.trim()).toBe('')
  })
})
