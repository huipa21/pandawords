import { randomUUID } from 'node:crypto'
import { expect, test } from '@playwright/test'
import { createApiClient } from '../src/api/client'
import { fillCredential, login, requiredCredential } from './review-session.helpers'

test('private reading highlights and bounded graphs work on desktop and mobile', async ({ page, baseURL }) => {
  test.setTimeout(120_000)
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ theme: 'system', locale: 'en' }))
  })
  await page.goto('/login')
  const admin = await login(page, requiredCredential('ADMIN_USERNAME'), requiredCredential('ADMIN_PASSWORD'))
  const adminApi = createApiClient({
    baseUrl: baseURL,
    auth: {
      getAccessToken: () => admin.access_token,
      refresh: async () => null,
      logout: () => {},
    },
  })
  let learnerId: string | undefined
  let projectId: string | undefined
  let passageId: string | undefined
  let api: ReturnType<typeof createApiClient> | undefined
  try {
    const username = `e2e_context_${randomUUID().replaceAll('-', '')}`
    const created = await adminApi.POST('/api/admin/users', {
      body: { username, role: 'user' },
    })
    expect(created.response.ok, 'Create an isolated context learner.').toBe(true)
    const learner = created.data
    if (!learner?.temporary_password || learner.user.username !== username || learner.user.id === admin.user.id)
      throw new Error('Expected the isolated learner and temporary password.')
    learnerId = learner.user.id
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page).toHaveURL('/login')
    await login(page, username, learner.temporary_password)
    await expect(page).toHaveURL('/change-password')
    await fillCredential(page.getByLabel(/^Current password\b/), learner.temporary_password)
    await fillCredential(page.getByLabel(/^New password\b/), randomUUID())
    const changing = page.waitForResponse(response =>
      response.url().endsWith('/api/auth/password') && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Change password', exact: true }).click()
    const changed = await changing
    expect(changed.ok()).toBe(true)
    const auth = await changed.json() as typeof admin
    expect(auth.user.id).toBe(learnerId)
    api = createApiClient({
      baseUrl: baseURL,
      auth: {
        getAccessToken: () => auth.access_token,
        refresh: async () => null,
        logout: () => {},
      },
    })
    const projectName = `Context ${randomUUID()}`
    const project = await api.POST('/api/projects', {
      body: {
        name: projectName,
        description: '',
        target_lang: 'en',
        source_lang: 'zh',
      },
    })
    projectId = project.data?.id
    if (!projectId)
      throw new Error('Expected the isolated project.')
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

    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/reading')
    await page.getByRole('textbox', { name: 'Passage title', exact: true }).fill('Context browser fixture')
    await page.getByRole('textbox', { name: 'Source', exact: true }).fill('Offline synthetic fixture')
    await page.getByRole('textbox', { name: 'Original passage', exact: true }).fill('🙂 cats bank xyzunknown!\nCat.')
    const ingesting = page.waitForResponse(response =>
      response.url().endsWith('/api/content/ingest') && response.request().method() === 'POST',
    )
    await page.getByRole('button', { name: 'Save and read', exact: true }).click()
    const ingested = await ingesting
    expect(ingested.ok()).toBe(true)
    const content = await ingested.json() as { passage: { id: string } }
    passageId = content.passage.id
    await expect(page).toHaveURL(`/reading/${passageId}`)
    const article = page.getByRole('article', { name: 'Original passage', exact: true })
    await expect(article).toContainText('🙂 cats bank xyzunknown!')
    await page.locator('[aria-label="Highlight vocabulary from project"]').click()
    await page.getByText(projectName, { exact: true }).last().click()
    await expect(article.getByRole('button', { name: 'cats: Visible selected sense', exact: true })).toBeVisible()
    await expect(article.getByRole('button', { name: 'bank: No confirmed sense', exact: true })).toBeVisible()
    await expect(article).toBeVisible()
    await expect(page.getByRole('navigation', { name: 'Bottom navigation', exact: true })).toBeVisible()
    await page.screenshot({
      path: test.info().outputPath('reading-mobile.png'),
      fullPage: true,
    })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)

    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto(`/projects/${projectId}`)
    await page.getByRole('button', { name: 'Graph', exact: true }).click()
    await page.getByTestId('graph-explorer').getByRole('button', { name: 'cat', exact: true }).click()
    await expect(page.getByTestId('graph-canvas')).toBeVisible()
    await expect(page.getByText('Keyboard and touch node list (2)', { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Tree', exact: true }).click()
    await expect(page.getByTestId('project-tree')).toBeVisible()
    await page.getByRole('button', { name: 'Graph', exact: true }).click()
    await expect(page.getByTestId('graph-canvas')).toBeVisible()
    await page.goto('/words')
    await page.getByRole('textbox', { name: 'Search visible vocabulary', exact: true }).fill('cat')
    await page.getByRole('button', { name: 'Search visible vocabulary', exact: true }).click()
    await page.getByTestId('graph-explorer').getByRole('button', { name: 'cat', exact: true }).click()
    await expect(page.getByTestId('graph-canvas')).toBeVisible()
    await page.screenshot({
      path: test.info().outputPath('graph-desktop.png'),
      fullPage: true,
    })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/words')
    await page.getByRole('textbox', { name: 'Search visible vocabulary', exact: true }).fill('cat')
    await page.getByRole('button', { name: 'Search visible vocabulary', exact: true }).click()
    await page.getByTestId('graph-explorer').getByRole('button', { name: 'cat', exact: true }).click()
    await expect(page.getByTestId('graph-canvas')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({
      path: test.info().outputPath('graph-mobile.png'),
      fullPage: true,
    })
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/dev/design')
    for (const theme of ['light', 'dark']) {
      const preview = page.locator(`[data-preview-theme="${theme}"] [data-testid="graph-preview"]`)
      await expect(preview).toBeVisible()
      await preview.screenshot({
        path: test.info().outputPath(`graph-preview-${theme}.png`),
      })
    }
  }
  finally {
    if (api && passageId) {
      const deleted = await api.DELETE('/api/content/{kind}/{id}', {
        params: {
          path: { kind: 'passage', id: passageId },
        },
      })
      expect(deleted.response.status, 'Delete only the test-created passage.').toBe(204)
    }
    if (api && projectId) {
      const deleted = await api.DELETE('/api/projects/{id}', {
        params: {
          path: { id: projectId },
        },
      })
      expect(deleted.response.status, 'Delete only the test-created project.').toBe(204)
    }
    if (learnerId) {
      const disabled = await adminApi.PATCH('/api/admin/users/{id}', {
        params: {
          path: { id: learnerId },
        },
        body: { disabled: true, reset_password: false },
      })
      expect(disabled.data?.user.disabled, 'Disable only the test-created learner.').toBe(true)
    }
  }
})
