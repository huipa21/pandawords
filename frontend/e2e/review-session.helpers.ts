import type { Locator, Page } from '@playwright/test'
import type { components } from '../src/api/schema'
import process from 'node:process'
import { expect } from '@playwright/test'

export function requiredCredential(name: 'ADMIN_USERNAME' | 'ADMIN_PASSWORD') {
  const value = process.env[name]
  if (!value)
    throw new Error(`E2E requires ${name} from the main worktree environment.`)
  return value
}

export async function fillCredential(input: Locator, value: string) {
  // Match first-login: never put credentials in Locator.fill failure call logs.
  await input.evaluate((element, secret) => {
    if (!(element instanceof HTMLInputElement))
      throw new TypeError('Expected a credential input.')
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(element, secret)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }, value)
}

export async function login(page: Page, username: string, password: string) {
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
