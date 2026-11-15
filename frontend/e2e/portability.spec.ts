import type { Page } from '@playwright/test'
import type { components } from '../src/api/schema'
import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { gunzipSync } from 'node:zlib'
import { expect, test } from '@playwright/test'
import { createApiClient } from '../src/api/client'
import { login, requiredCredential } from './review-session.helpers'

// Local paths, provider/media URLs and credential-like text must never reach the portability UI.
const LEAKS = /[A-Z]:\\|\/(?:data|app|home|tmp|var)\/|\/api\/media|https?:\/\/|bearer/i

async function expectNoLeaks(page: Page, secrets: string[]) {
  const text = await page.locator('body').textContent() ?? ''
  expect(text).not.toMatch(LEAKS)
  for (const secret of secrets)
    expect(text).not.toContain(secret)
  const sources = await page.locator('body [src], body [href]').evaluateAll(elements => elements.flatMap(element =>
    ['src', 'href'].map(name => element.getAttribute(name) ?? '').filter(Boolean)))
  for (const source of sources)
    expect(source, 'Media must be delivered through protected blob URLs.').not.toMatch(/\/api\/media|^https?:\/\/(?!localhost)/)
}

test('project export then import round-trips with progress enabled and disabled', async ({ page, baseURL }) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ theme: 'system', locale: 'en' }))
  })
  const password = requiredCredential('ADMIN_PASSWORD')
  await page.goto('/login')
  const auth = await login(page, requiredCredential('ADMIN_USERNAME'), password)
  await expect(page).toHaveURL('/projects')
  const secrets = [password, auth.access_token]
  const api = createApiClient({
    baseUrl: baseURL,
    auth: {
      getAccessToken: () => auth.access_token,
      refresh: async () => null,
      logout: () => {},
    },
  })
  const projectIds: string[] = []
  try {
    const project = await api.POST('/api/projects', {
      body: {
        name: `Portability ${randomUUID()}`,
        description: '',
        target_lang: 'en',
        source_lang: 'zh',
      },
    })
    const projectId = project.data?.id
    if (!projectId)
      throw new Error('Expected the isolated project.')
    projectIds.push(projectId)
    const candidates = await api.POST('/api/dictionary/candidates', {
      body: { text: 'cat' },
    })
    const candidate = candidates.data?.candidates[0]
    const sense = candidate?.lexemes[0]?.senses[0]
    if (!candidate || !sense)
      throw new Error('Expected the offline cat fixture.')
    const added = await api.POST('/api/projects/{id}/dictionary', {
      params: {
        path: { id: projectId },
      },
      body: {
        lemma_key: candidate.lemma.id,
        selected_senses: [sense.id],
      },
    })
    expect(added.response.ok).toBe(true)

    await page.goto(`/projects/${encodeURIComponent(projectId)}`)
    await expect(page.getByTestId('project-tree').locator('[data-tree-table="sense"]').first()).toBeVisible()
    const downloading = page.waitForEvent('download')
    const exporting = page.waitForResponse(response => response.url().includes('/export') && response.request().method() === 'GET')
    await page.getByTestId('project-export').click()
    expect((await exporting).status()).toBe(200)
    const download = await downloading
    expect(download.suggestedFilename()).toMatch(/^[^\\/]+\.pandawords-project\.tar\.gz$/)
    const archivePath = test.info().outputPath(download.suggestedFilename())
    await download.saveAs(archivePath)
    const contents = gunzipSync(await readFile(archivePath)).toString('latin1')
    for (const secret of secrets)
      expect(contents.includes(secret), 'The archive must not carry credentials.').toBe(false)
    await expect(page.getByText('Project archive downloaded.')).toBeVisible()
    await expectNoLeaks(page, secrets)

    for (const progress of [true, false]) {
      await page.goto('/projects')
      await page.getByTestId('project-import').click()
      const dialog = page.getByTestId('project-import-dialog')
      await dialog.getByTestId('archive-input').setInputFiles(archivePath)
      await expect(dialog.getByTestId('archive-file')).toContainText(download.suggestedFilename())
      await dialog.getByTestId(progress ? 'progress-on' : 'progress-off').click()
      // Chromium can evict the inspector copy of this response, so read it through the route.
      let imported: ((value: { status: number, summary: components['schemas']['ImportSummary'], url: string }) => void) | undefined
      const importing = new Promise<{ status: number, summary: components['schemas']['ImportSummary'], url: string }>((resolve) => {
        imported = resolve
      })
      await page.route('**/api/projects/import**', async (route) => {
        const upstream = await route.fetch()
        const body = await upstream.body()
        imported?.({
          status: upstream.status(),
          summary: JSON.parse(body.toString('utf8')) as components['schemas']['ImportSummary'],
          url: route.request().url(),
        })
        await route.fulfill({ response: upstream, body })
      })
      await dialog.getByTestId('archive-submit').click()
      const response = await importing
      await page.unroute('**/api/projects/import**')
      expect(new URL(response.url).searchParams.get('include_progress')).toBe(String(progress))
      expect(response.status, 'Import must succeed.').toBe(201)
      const summary = response.summary
      projectIds.push(...summary.project_ids)
      expect(summary.progress_imported).toBe(progress)
      expect(summary.project_ids).toHaveLength(1)
      expect(summary.project_ids[0]).not.toBe(projectId)

      const result = dialog.getByTestId('archive-summary')
      await expect(result).toContainText('Project imported.')
      await expect(result).toContainText(progress ? 'Learning progress was imported.' : 'Learning progress was not imported.')
      await expectNoLeaks(page, secrets)
      await dialog.getByTestId('archive-open-project').click()
      await expect(page).toHaveURL(`/projects/${encodeURIComponent(summary.project_ids[0]!)}`)
      await expect(page.getByTestId('project-tree').locator('[data-tree-table="sense"]').first()).toBeVisible()
      await expectNoLeaks(page, secrets)
    }
  }
  finally {
    for (const id of projectIds) {
      const removed = await api.DELETE('/api/projects/{id}', {
        params: {
          path: { id },
        },
      })
      expect(removed.response.status, 'Delete only the test-created projects.').toBe(204)
    }
  }
})
