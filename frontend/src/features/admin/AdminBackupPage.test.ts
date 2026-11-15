import type { SiteBackupStatus } from './useSiteBackups'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import AppNavigation from '@/components/app/AppNavigation.vue'
import { authPayload } from '@/features/auth/testHarness'
import { apiError, blobResult, captureDownloads, clickText, mountPage, query } from '@/features/portability/testHarness'
import { useAuthStore } from '@/stores/auth'
import AdminBackupPage from './AdminBackupPage.vue'
import { POLL_MS } from './useSiteBackups'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
}))
vi.mock('@/api/client', async original => ({
  ...await original<typeof import('@/api/client')>(),
  api: client,
}))

const backup = {
  name: 'pandawords-site-20261115.tar.gz',
  created_at: '2026-11-15T10:00:00Z',
  size: 2048,
  sha256: 'a'.repeat(64),
}
function status(overrides: Partial<SiteBackupStatus> = {}) {
  return {
    data: {
      running: false,
      last_error: null,
      backups: [],
      ...overrides,
    },
    response: new Response(null, { status: 200 }),
  }
}

let cleanup: (() => void) | undefined
async function setup(locale: 'en' | 'zh-CN' = 'en') {
  const mounted = await mountPage(AdminBackupPage, locale)
  cleanup = mounted.cleanup
}
const text = () => document.body.textContent ?? ''

beforeEach(() => {
  vi.clearAllMocks()
  client.GET.mockResolvedValue(status())
})
afterEach(() => {
  cleanup?.()
  cleanup = undefined
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('admin site backup', () => {
  it('renders loading, localized load errors with retry, and the empty state', async () => {
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    await setup('zh-CN')
    expect(query('[role="status"][aria-label]').getAttribute('aria-label')).toBe('加载中')
    resolve(apiError('auth.forbidden', 403))
    await flushPromises()
    expect(text()).toContain('你没有执行此操作的权限。')
    expect(text()).not.toContain('NEVER DISPLAY')
    await clickText('重试')
    expect(text()).toContain('暂无站点备份。')
    expect(document.body.querySelector('input[type="file"]')).toBeNull()
  })

  it('creates a backup, polls while it runs, then lists it for download', async () => {
    vi.useFakeTimers({
      toFake: ['setTimeout', 'clearTimeout'],
    })
    await setup()
    expect(text()).toContain('No site backups yet.')
    expect(text()).toContain('deploy/restore.sh')
    client.POST.mockResolvedValueOnce(status({ running: true }))
    await clickText('Create backup')
    expect(client.POST).toHaveBeenCalledWith('/api/admin/backups')
    expect(query('[data-testid="site-backup-status"]').textContent).toContain('A backup is running.')
    expect(query('[data-testid="site-backup-start"]').hasAttribute('disabled')).toBe(true)
    client.GET.mockResolvedValueOnce(status({ running: true }))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    expect(client.GET).toHaveBeenCalledTimes(2)
    client.GET.mockResolvedValueOnce(status({
      backups: [backup],
    }))
    await vi.advanceTimersByTimeAsync(POLL_MS)
    await flushPromises()
    expect(client.GET).toHaveBeenCalledTimes(3)
    expect(text()).toContain(backup.name)
    expect(text()).toContain('2.0 KB')
    await vi.advanceTimersByTimeAsync(POLL_MS * 3)
    expect(client.GET).toHaveBeenCalledTimes(3)

    const saved = captureDownloads()
    client.GET.mockResolvedValueOnce(blobResult(backup.name))
    query('[data-testid="site-backup-download"]').click()
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/admin/backups/{name}', {
      params: {
        path: { name: backup.name },
      },
      parseAs: 'blob',
      signal: expect.any(AbortSignal),
    })
    expect(saved).toEqual([backup.name])
    expect(text()).not.toContain('blob:')
  })

  it('reports a concurrent backup conflict, a failed stage, and a missing download', async () => {
    client.GET.mockResolvedValue(status({
      last_error: 'database',
      backups: [backup],
    }))
    await setup()
    expect(query('[data-testid="site-backup-status"]').textContent).toContain('The last backup failed at: database export')
    client.POST.mockResolvedValueOnce(apiError('site_backup.in_progress', 409))
    await clickText('Create backup')
    expect(query('[data-testid="site-backup-error"]').textContent).toContain('A site backup or restore is already running.')
    expect(client.GET).toHaveBeenCalledTimes(2)
    client.GET.mockResolvedValueOnce(apiError('site_backup.not_found', 404))
    query('[data-testid="site-backup-download"]').click()
    await flushPromises()
    expect(query('[data-testid="site-backup-error"]').textContent).toContain('This backup no longer exists.')
    expect(text()).not.toContain('NEVER DISPLAY')
  })
})

describe('site backup visibility', () => {
  it.each([
    ['user', false],
    ['admin', true],
  ] as const)('shows site-backup navigation to %s: %s', async (role, visible) => {
    const page = defineComponent({
      setup: () => () => h(AppNavigation),
    })
    const mounted = await mountPage(page)
    cleanup = mounted.cleanup
    useAuthStore().user = authPayload({ role }).user
    await flushPromises()
    const links = Array.from(document.body.querySelectorAll('a')).map(link => link.getAttribute('href'))
    expect(links.includes('/admin/backup')).toBe(visible)
    expect(links).toContain('/settings')
  })
})
