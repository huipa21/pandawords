import { expect, test } from '@playwright/test'

for (const locale of ['en', 'zh-CN']) {
  test(`offline IndexedDB queue survives reconnect, lost receipt and logout: ${locale}`, async ({ page, context }) => {
    let grades = 0
    let confirms = 0
    let receipts = 0
    let clientKey: string | undefined
    const attempt = {
      id: 'a'.repeat(32),
      project_id: 'project-fixture',
      sense_id: 'sense-fixture',
      exercise: 'cloze',
      kind: 'recall',
      status: 'open',
      prompt: { text: 'Complete: I ____ every day.', input: 'text', choices: [] },
      issued_at: new Date().toISOString(),
      expires_at: new Date(Date.now() + 86400_000).toISOString(),
      hint_used: false,
      hint: null,
      skipped: [],
    }
    await context.addInitScript((locale) => {
      localStorage.setItem('pandawords.preferences', JSON.stringify({ locale, theme: 'light' }))
    }, locale)
    await context.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname
      if (path === '/api/auth/refresh') {
        await route.fulfill({
          json: {
            access_token: 'fixture-token',
            token_type: 'bearer',
            user: {
              id: 'offline-learner',
              username: 'offline-learner',
              role: 'user',
              must_change_password: false,
            },
          },
        })
      }
      else if (path.endsWith('/offline')) {
        await route.fulfill({
          json: {
            project_id: attempt.project_id,
            attempts: [attempt],
            lease_seconds: 86400,
            active_limit: 20,
          },
        })
      }
      else if (path.endsWith('/answer')) {
        grades++
        const answer = route.request().postDataJSON()
        expect(answer.answer).toBe('practice')
        clientKey ??= answer.client_key
        expect(answer.client_key).toBe(clientKey)
        await route.fulfill({
          json: {
            ...attempt,
            status: 'graded',
            auto_rating: 3,
            feedback: { correct: true, answer: 'practice' },
            duration_ms: answer.duration_ms,
            server_elapsed_ms: 10000,
          },
        })
      }
      else if (path.endsWith('/confirm')) {
        confirms++
        receipts = 1
        if (confirms === 1) {
          await route.abort('connectionreset')
          return
        }
        await route.fulfill({
          json: {
            ...attempt,
            status: 'confirmed',
            receipt: { attempt_id: attempt.id },
            auto_rating: 3,
          },
        })
      }
      else {
        await route.fulfill({ status: 204 })
      }
    })
    await page.goto(`/projects/${attempt.project_id}/offline-review`)
    const prepare = page.getByRole('button', {
      name: locale === 'en'
        ? 'Prepare prompts online'
        : '联网预备题目',
      exact: true,
    })
    await prepare.click()
    await expect(page.getByText(attempt.prompt.text)).toBeVisible()
    await context.setOffline(true)
    await expect(page.locator('[data-state="offline"]')).toBeVisible()
    await page.getByRole('textbox').fill('practice')
    await page.getByRole('button', {
      name: locale === 'en'
        ? 'Submit answer'
        : '提交答案',
      exact: true,
    }).click()
    await expect(page.getByText(locale === 'en'
      ? 'Saved answer: practice'
      : '已保存的答案：practice', { exact: true })).toBeVisible()
    expect(grades).toBe(0)
    await expect(page.locator('[data-state="offline"]')).toContainText(locale === 'en'
      ? 'Receipts: 0'
      : '已确认：0')
    await context.setOffline(false)
    await expect(page.locator('[data-state="failed"]')).toBeVisible()
    const stored = await page.evaluate(async () => {
      const db = await new Promise<IDBDatabase>((resolve) => {
        const request = indexedDB.open('pandawords-offline-review-v1')
        request.onsuccess = () => resolve(request.result)
      })
      const data = await new Promise<unknown>((resolve) => {
        const request = db.transaction('owners').objectStore('owners').get('offline-learner')
        request.onsuccess = () => resolve(request.result)
      })
      db.close()
      return JSON.stringify(data)
    })
    expect(stored).not.toContain('feedback')
    expect(stored).not.toContain('fixture-token')
    await page.getByRole('button', {
      name: locale === 'en'
        ? 'Sync with suggested ratings'
        : '采用建议评级同步',
      exact: true,
    }).click()
    await expect(page.locator('[data-state="online"]')).toContainText(locale === 'en'
      ? 'Receipts: 1'
      : '已确认：1')
    expect(grades).toBe(1)
    expect(confirms).toBe(2)
    expect(receipts).toBe(1)
    const cached = await page.evaluate(async () => (await Promise.all(
      (await caches.keys()).map(async key => (await (await caches.open(key)).keys()).map(request => request.url)),
    )).flat())
    expect(cached.every(url => !url.includes('/api/'))).toBe(true)
    await page.getByRole('button', {
      name: locale === 'en'
        ? 'Sign out'
        : '退出登录',
      exact: true,
    }).click()
    await expect(page).toHaveURL(/\/login/)
    const ownerRows = await page.evaluate(async () => {
      const request = indexedDB.open('pandawords-offline-review-v1')
      const db = await new Promise<IDBDatabase>((resolve) => {
        request.onsuccess = () => resolve(request.result)
      })
      const rows = await new Promise<unknown[]>((resolve) => {
        const read = db.transaction('owners').objectStore('owners').getAll()
        read.onsuccess = () => resolve(read.result)
      })
      db.close()
      return rows
    })
    expect(ownerRows).toEqual([])
  })
}
