import type { Locator, Page } from '@playwright/test'
import type { components } from '../src/api/schema'
import { randomUUID } from 'node:crypto'
import process from 'node:process'
import { expect, test } from '@playwright/test'
import { createApiClient } from '../src/api/client'

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

async function login(page: Page, username: string, password: string) {
  await fillCredential(page.getByLabel(/^Username\b/), username)
  await fillCredential(page.getByLabel(/^Password\b/), password)
  const response = page.waitForResponse(response =>
    response.url().endsWith('/api/auth/login') && response.request().method() === 'POST',
  )
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  const result = await response
  expect(result.ok(), 'UI login must succeed.').toBe(true)
  return await result.json() as components['schemas']['AuthRead']
}

test('administrator creates a learner who must change their temporary password', async ({ page, baseURL }) => {
  const adminUsername = requiredCredential('ADMIN_USERNAME')
  const adminPassword = requiredCredential('ADMIN_PASSWORD')
  const username = `e2e_${randomUUID().replaceAll('-', '')}`
  const newPassword = randomUUID()

  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ theme: 'system', locale: 'en' }))
  })
  await page.goto('/login')
  const admin = await login(page, adminUsername, adminPassword)
  await expect(page).toHaveURL('/projects')

  const api = createApiClient({
    baseUrl: baseURL,
    auth: {
      getAccessToken: () => admin.access_token,
      refresh: async () => null,
      logout: () => {},
    },
  })
  let createdUser: components['schemas']['UserRead'] | undefined
  try {
    await page.getByRole('link', { name: 'User management', exact: true }).click()
    await page.getByRole('button', { name: 'Create user', exact: true }).click()
    const createDialog = page.getByRole('dialog', { name: 'Create user', exact: true })
    await createDialog.getByLabel(/^Username\b/).fill(username)
    const creation = page.waitForResponse(response =>
      response.url().endsWith('/api/admin/users') && response.request().method() === 'POST',
    )
    await createDialog.getByRole('button', { name: 'Create user', exact: true }).click()
    const response = await creation
    expect(response.ok(), 'UI user creation must succeed.').toBe(true)
    const result = await response.json() as components['schemas']['AdminUserResult']
    if (result.user.username !== username || result.user.id === admin.user.id)
      throw new Error('Creation did not return the isolated E2E learner.')
    createdUser = result.user

    const passwordDialog = page.getByRole('dialog', { name: 'Temporary password', exact: true })
    await expect(passwordDialog).toBeVisible()
    const temporaryPassword = await passwordDialog.getByLabel('Temporary password', { exact: true }).textContent()
    if (!temporaryPassword)
      throw new Error('The temporary-password dialog must provide a password.')
    await passwordDialog.getByRole('button', { name: 'Done', exact: true }).click()
    await page.getByRole('button', { name: 'Sign out', exact: true }).click()
    await expect(page).toHaveURL('/login')

    const learner = await login(page, username, temporaryPassword)
    expect(learner.user.id === createdUser.id, 'Login must grant the created learner session.').toBe(true)
    expect(learner.user.must_change_password, 'Public login must expose the forced-change flag.').toBe(true)
    await expect(page).toHaveURL('/change-password')
    await expect(page.getByText('Change your temporary password before continuing.', { exact: true })).toBeVisible()
    await page.getByRole('link', { name: 'PandaWords', exact: true }).click()
    await expect(page).toHaveURL('/change-password')
    await fillCredential(page.getByLabel(/^Current password\b/), temporaryPassword)
    await fillCredential(page.getByLabel(/^New password\b/), newPassword)
    await page.getByRole('button', { name: 'Change password', exact: true }).click()
    await expect(page).toHaveURL('/projects')
    await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible()
  }
  finally {
    if (createdUser) {
      const cleanup = await api.PATCH('/api/admin/users/{id}', {
        params: {
          path: { id: createdUser.id },
        },
        body: { disabled: true, reset_password: false },
      })
      expect(cleanup.data?.user.disabled === true, 'Disable the isolated E2E learner; otherwise administrator cleanup is required.').toBe(true)
    }
  }
})
