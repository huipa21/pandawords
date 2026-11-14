import type { Locator, Page } from '@playwright/test'
import type { components } from '../src/api/schema'
import { randomUUID } from 'node:crypto'
import process from 'node:process'
import { expect, test } from '@playwright/test'
import { createApiClient } from '../src/api/client'

const FIXTURE_WORD = 'run'

function requiredCredential(name: 'ADMIN_USERNAME' | 'ADMIN_PASSWORD') {
  const value = process.env[name]
  if (!value)
    throw new Error(`E2E requires ${name} from the main worktree environment.`)
  return value
}

async function fillCredential(input: Locator, value: string) {
  // Locator.fill failure call logs include its argument. Keep credentials out of them.
  await input.evaluate((element, secret) => {
    if (!(element instanceof HTMLInputElement))
      throw new TypeError('Expected a credential input.')
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(element, secret)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }, value)
}

async function login(page: Page) {
  await fillCredential(page.getByLabel(/^Username\b/), requiredCredential('ADMIN_USERNAME'))
  await fillCredential(page.getByLabel(/^Password\b/), requiredCredential('ADMIN_PASSWORD'))
  const response = page.waitForResponse(response =>
    response.url().endsWith('/api/auth/login') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  const result = await response
  expect(result.ok(), 'UI login must succeed.').toBe(true)
  return await result.json() as components['schemas']['AuthRead']
}

test('learner adds a fixture word, overrides a sense and hides it from the project tree', async ({ page, baseURL }) => {
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ theme: 'system', locale: 'en' }))
  })
  await page.goto('/login')
  const auth = await login(page)
  await expect(page).toHaveURL('/projects')

  const api = createApiClient({
    baseUrl: baseURL,
    auth: {
      getAccessToken: () => auth.access_token,
      refresh: async () => null,
      logout: () => {},
    },
  })
  const projectName = `e2e-${randomUUID()}`
  let projectId: string | undefined
  try {
    await page.getByTestId('project-create').click()
    await page.locator('#project-name').fill(projectName)
    const creation = page.waitForResponse(response =>
      response.url().endsWith('/api/projects') && response.request().method() === 'POST',
    )
    await page.getByTestId('project-save').click()
    const created = await creation
    expect(created.ok(), 'Project creation must succeed.').toBe(true)
    projectId = (await created.json() as components['schemas']['ProjectRead']).id
    await expect(page.getByTestId('project-detail')).toBeVisible()

    await page.getByTestId('project-add-word').click()
    const dialog = page.getByTestId('add-word-dialog')
    await dialog.getByTestId('add-word-input').fill(FIXTURE_WORD)
    await dialog.getByTestId('add-word-search').click()
    const submit = dialog.getByTestId('add-word-submit')
    await expect(submit).toBeVisible()
    if (await submit.isDisabled())
      await dialog.getByRole('checkbox').first().check()
    await expect(submit).toBeEnabled()
    await submit.click()
    await expect(dialog.getByTestId('add-word-success')).toBeVisible()
    await dialog.getByTestId('add-word-close').click()

    const tree = page.getByTestId('project-tree')
    await expect(tree.locator('[data-tree-table="sense"]').first()).toBeVisible()
    await tree.getByTestId('project-tree-word-link').first().click()
    await expect(page).toHaveURL(/\/words\//)
    const lemmaId = decodeURIComponent(new URL(page.url()).pathname.split('/').pop() ?? '')

    const detail = page.getByTestId('word-detail')
    const sense = detail.getByTestId('word-sense').first()
    const senseId = await sense.getAttribute('data-sense-id')
    if (!senseId)
      throw new Error('The word detail page must expose sense ids.')
    const changed = `E2E override ${randomUUID()}`
    await sense.getByTestId('word-sense-edit').click()
    const editor = page.getByTestId('word-override-editor')
    await editor.locator('#word-override-definition').fill(changed)
    await editor.getByTestId('word-override-save').click()
    await expect(editor).toBeHidden()
    await expect(detail.locator(`[data-sense-id="${senseId}"]`)).toContainText(changed)

    await page.reload()
    await expect(detail.locator(`[data-sense-id="${senseId}"]`)).toContainText(changed)

    await page.goto(`/projects/${encodeURIComponent(projectId)}`)
    const senseNode = tree.locator(`[data-tree-table="sense"][data-tree-id="${senseId}"]`)
    await expect(senseNode).toBeVisible()
    await senseNode.getByTestId('project-tree-visibility').click()
    await expect(tree.getByTestId('project-tree-undo')).toBeVisible()
    await expect(senseNode).toHaveCount(0)

    await tree.getByTestId('project-tree-show-hidden').click()
    await expect(senseNode).toBeVisible()

    const entry = await api.GET('/api/dictionary/lemmas/{lemma_id}/entry', {
      params: {
        path: { lemma_id: lemmaId },
      },
    })
    expect(entry.response.ok, 'Hiding must not delete dictionary data.').toBe(true)
    expect(JSON.stringify(entry.data)).toContain(senseId)
    expect(JSON.stringify(entry.data)).toContain(changed)
  }
  finally {
    if (projectId) {
      const removed = await api.DELETE('/api/projects/{id}', {
        params: {
          path: { id: projectId },
        },
      })
      expect(removed.response.ok, 'E2E project cleanup must succeed.').toBe(true)
    }
  }
})
