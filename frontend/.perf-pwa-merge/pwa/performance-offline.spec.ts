import { expect, test } from '@playwright/test'

test('lazy project graph and login shell remain available offline', async ({ page, context }) => {
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ locale: 'en', theme: 'light' }))
  })
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    const user = {
      id: 'user:fixture',
      username: 'fixture',
      role: 'user',
      disabled: false,
      must_change_password: false,
      source_lang: 'zh',
      target_lang: 'en',
      prefs: { theme: 'light', locale: 'en', accent: 'US', desired_retention: 0.9 },
    }
    if (path === '/api/auth/refresh')
      return route.fulfill({ json: { access_token: 'fixture', token_type: 'bearer', user } })
    if (path.endsWith('/tree'))
      return route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } })
    if (path === '/api/projects/performance')
      return route.fulfill({
        json: {
          id: 'performance',
          name: 'Performance project',
          description: '',
          target_lang: 'en',
          source_lang: 'zh',
          plan: { daily_new: 20 },
          created_at: '2026-11-14T00:00:00Z',
        },
      })
    return route.fulfill({ status: 404, json: { code: 'not_found' } })
  })
  await page.goto('/projects/performance')
  await expect(page.getByTestId('project-detail')).toBeVisible()
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true)
  await expect(page.getByTestId('project-detail')).toBeVisible()
  await context.unroute('**/api/**')
  await context.setOffline(true)
  await page.getByRole('button', { name: 'Graph', exact: true }).click()
  await expect(page.getByTestId('graph-explorer')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('The graph is unavailable')
  await page.getByRole('button', { name: 'Tree', exact: true }).click()
  await expect(page.getByTestId('graph-explorer')).toHaveCount(0)
  const cached = await page.evaluate(async () => {
    const names = await caches.keys()
    const lists = await Promise.all(names.map(async name => (await (await caches.open(name)).keys())
      .map(request => new URL(request.url).pathname)))
    return lists.flat()
  })
  expect(cached.some(path => path.startsWith('/api/'))).toBe(false)
  await page.goto('/projects/performance')
  await expect(page.locator('#username')).toBeVisible()
  await expect(page).toHaveURL(/\/login$/)
})
