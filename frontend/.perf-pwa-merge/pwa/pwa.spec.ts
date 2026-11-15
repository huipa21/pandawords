import { createHash } from 'node:crypto'
import { expect, test } from '@playwright/test'

test('production manifest/icons install and offline shell never cache private traffic; online login is unchanged', async ({ page, context, request }) => {
  const manifestResponse = await request.get('/manifest.v1.webmanifest')
  expect(manifestResponse.ok()).toBe(true)
  const manifest = await manifestResponse.json()
  expect(manifest).toMatchObject({
    id: '/',
    name: 'PandaWords',
    short_name: 'PandaWords',
    start_url: '/',
    scope: '/',
    display: 'standalone',
  })
  expect(manifest.theme_color).toMatch(/^#[\da-f]{6}$/i)
  expect(manifest.background_color).toMatch(/^#[\da-f]{6}$/i)
  expect(manifest.icons).toHaveLength(2)
  for (const icon of manifest.icons) {
    const response = await request.get(icon.src)
    expect(response.headers()['content-type']).toContain('image/png')
    const png = await response.body()
    expect(png.subarray(0, 8).toString('hex')).toBe('89504e470d0a1a0a')
    expect(`${png.readUInt32BE(16)}x${png.readUInt32BE(20)}`).toBe(icon.sizes)
    expect(icon.purpose).toContain('maskable')
  }
  const workerSource = await (await request.get('/sw.js')).text()
  const precache = JSON.parse(workerSource.match(/^const precache = (.+)$/m)![1]!) as { url: string, integrity: string }[]
  const publicFiles = [
    '/index.html',
    '/manifest.v1.webmanifest',
    '/pwa-install.v1.js',
    '/icons/panda.v1.192.png',
    '/icons/panda.v1.512.png',
  ]
  expect(precache.length).toBeGreaterThan(5)
  for (const entry of precache) {
    if (!publicFiles.includes(entry.url)) {
      expect(entry.url.startsWith('/assets/')).toBe(true)
      expect(entry.url).toMatch(/-[\w-]{8,}\.\w+$/)
      expect([
        'js',
        'css',
        'woff',
        'woff2',
        'png',
        'svg',
        'webp',
      ]).toContain(entry.url.split('.').at(-1))
    }
    const response = await request.get(entry.url)
    expect(response.ok()).toBe(true)
    expect(entry.integrity).toBe(`sha256-${createHash('sha256').update(await response.body()).digest('base64')}`)
  }
  await context.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (path === '/api/auth/login') {
      await route.fulfill({
        json: {
          access_token: 'test-token',
          token_type: 'bearer',
          user: {
            id: 'user:test',
            username: 'test-learner',
            role: 'user',
            must_change_password: false,
          },
        },
      })
    }
    else if (path === '/api/auth/refresh') {
      await route.fulfill({
        status: 401,
        json: { code: 'auth.unauthorized', message: 'Unauthorized' },
      })
    }
    else if (path === '/api/projects') {
      await route.fulfill({
        json: {
          items: [],
          total: 0,
          page: 1,
          page_size: 20,
        },
      })
    }
    else {
      await route.fulfill({
        json: { secret: 'private-response-never-cache' },
      })
    }
  })
  await page.goto('/projects/private-route')
  await expect(page).toHaveURL(/\/login$/)
  await page.evaluate(() => navigator.serviceWorker.ready)
  await page.reload()
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true)
  const cdp = await context.newCDPSession(page)
  expect((await cdp.send('Page.getAppManifest')).errors).toEqual([])
  expect((await cdp.send('Page.getInstallabilityErrors')).installabilityErrors).toEqual([])
  await cdp.detach()
  await expect(page.locator('#username')).toBeVisible()
  await page.locator('#username').fill('test-learner')
  await page.locator('#password').fill('test-password')
  await page.locator('form button[type="submit"]').click()
  await expect(page).toHaveURL(/\/projects$/)
  await page.evaluate(async () => {
    await fetch('/api/private-record', {
      headers: { Authorization: 'Bearer test-token' },
    })
    await fetch('/api/media/owner-image')
    await fetch('/_media/private-image')
    await fetch('/media/private-image')
  })
  const cached = await page.evaluate(async () => {
    const result: { url: string, text?: string }[] = []
    for (const name of await caches.keys()) {
      const cache = await caches.open(name)
      for (const key of await cache.keys()) {
        const response = await cache.match(key)
        const text = response?.headers.get('content-type')?.includes('text/html')
          ? await response.text()
          : ''
        result.push({ url: new URL(key.url).pathname, text })
      }
    }
    return result
  })
  expect(cached.length).toBeGreaterThan(5)
  expect(cached.some(entry => entry.url === '/index.html')).toBe(true)
  expect(cached.map(entry => entry.url).sort()).toEqual(precache.map(entry => entry.url).sort())
  for (const entry of cached) {
    expect(entry.text).not.toContain('private-response-never-cache')
    expect(entry.text).not.toContain('test-learner')
  }
  await context.unroute('**/api/**')
  await context.setOffline(true)
  try {
    await page.goto('/projects/private-route')
    await expect(page.locator('#username')).toBeVisible()
    await expect(page).toHaveURL(/\/login$/)
    expect(await page.evaluate(() => document.querySelectorAll('script[src]').length)).toBeGreaterThan(0)
    expect(await page.evaluate(async () => {
      try {
        await fetch('/api/media/owner-image', {
          headers: { Authorization: 'Bearer test-token' },
        })
        return 'unexpected-response'
      }
      catch {
        return 'network-unavailable'
      }
    })).toBe('network-unavailable')
  }
  finally {
    await context.setOffline(false)
  }
})

test('captures an early install event and invokes the native prompt from the keyboard', async ({ page, context }) => {
  let releaseApp!: () => void
  let appRequested!: () => void
  const gate = new Promise<void>(resolve => releaseApp = resolve)
  const requested = new Promise<void>(resolve => appRequested = resolve)
  await context.route(/\/assets\/index-[^/]+\.js$/, async (route) => {
    appRequested()
    await gate
    await route.continue()
  })
  await context.route('**/api/**', route => route.fulfill({
    status: 401,
    json: { code: 'auth.unauthorized' },
  }))
  await page.addInitScript(() => {
    localStorage.setItem('pandawords.preferences', JSON.stringify({ locale: 'en', theme: 'light' }))
  })
  try {
    await page.goto('/login', { waitUntil: 'commit' })
    await requested
    await page.waitForFunction(() => '__pandawordsInstall' in window)
    expect(await page.evaluate(() => {
      const state = window as Window & { testInstallCalls?: number }
      state.testInstallCalls = 0
      const event = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
        prompt: async () => { state.testInstallCalls = (state.testInstallCalls ?? 0) + 1 },
        userChoice: Promise.resolve({ outcome: 'accepted' }),
      })
      window.dispatchEvent(event)
      return event.defaultPrevented
    })).toBe(true)
  }
  finally {
    releaseApp()
  }
  const install = page.getByRole('button', { name: 'Install', exact: true })
  await expect(install).toBeVisible()
  await install.focus()
  await page.keyboard.press('Enter')
  await expect.poll(() => page.evaluate(() => (window as Window & { testInstallCalls?: number }).testInstallCalls)).toBe(1)
  await expect(install).toHaveCount(0)
  await expect(page.locator('#username')).toBeVisible()
})

for (const locale of ['en', 'zh-CN'] as const) {
  for (const width of [320, 1280]) {
    test(`install prompt keyboard, localization and layout: ${locale} ${width}`, async ({ page, context }) => {
      await page.setViewportSize({ width, height: 800 })
      await context.route('**/api/**', route => route.fulfill({
        status: 401,
        json: { code: 'auth.unauthorized' },
      }))
      await page.addInitScript((language) => {
        localStorage.setItem('pandawords.preferences', JSON.stringify({ locale: language, theme: 'light' }))
        window.addEventListener('beforeinstallprompt', (event) => {
          if (event.isTrusted) {
            event.preventDefault()
            event.stopImmediatePropagation()
          }
        })
      }, locale)
      await page.goto('/login')
      await expect(page.locator('#username')).toBeVisible()
      await expect(page.locator('#pwa-install-title')).toHaveCount(0)
      await page.evaluate(() => {
        const event = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
          prompt: async () => {},
          userChoice: Promise.resolve({ outcome: 'accepted' }),
        })
        window.dispatchEvent(event)
      })
      const title = page.getByRole('heading', {
        name: locale === 'en'
          ? 'Install PandaWords'
          : '安装 PandaWords',
      })
      await expect(title).toBeVisible()
      const install = page.getByRole('button', {
        name: locale === 'en'
          ? 'Install'
          : '安装',
        exact: true,
      })
      const dismiss = page.getByRole('button', {
        name: locale === 'en'
          ? 'Not now'
          : '暂不安装',
        exact: true,
      })
      for (const control of [install, dismiss]) {
        const bounds = await control.boundingBox()
        expect(bounds!.height).toBeGreaterThanOrEqual(44)
        expect(bounds!.width).toBeGreaterThanOrEqual(44)
        expect(bounds!.x).toBeGreaterThanOrEqual(0)
        expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width)
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
      await install.focus()
      await page.keyboard.press('Tab')
      await expect(dismiss).toBeFocused()
      const focus = await dismiss.evaluate((element) => {
        const style = getComputedStyle(element)
        const tokens = getComputedStyle(document.documentElement)
        return {
          style: style.outlineStyle,
          width: style.outlineWidth,
          offset: style.outlineOffset,
          tokenWidth: tokens.getPropertyValue('--pw-focus-ring-width').trim(),
          tokenOffset: tokens.getPropertyValue('--pw-focus-ring-offset').trim(),
        }
      })
      expect(focus.style).toBe('solid')
      expect(focus.width).toBe(focus.tokenWidth)
      expect(focus.offset).toBe(focus.tokenOffset)
      await page.keyboard.press('Enter')
      await expect(title).toHaveCount(0)
      await expect(page.locator('#username')).toBeVisible()
      await page.reload()
      await page.evaluate(() => window.dispatchEvent(new Event('beforeinstallprompt')))
      await expect(title).toHaveCount(0)
    })
  }
}
