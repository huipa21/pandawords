import type { Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { createServer } from 'node:http'
import { extname, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { expect, test } from '@playwright/test'

async function updateFixture() {
  const dist = resolve(fileURLToPath(new URL('../dist/', import.meta.url)))
  const original = await readFile(resolve(dist, 'sw.js'), 'utf8')
  const version = original.match(/const cacheName = `\$\{cachePrefix\}([a-f0-9]{20})`/)?.[1]
  if (!version)
    throw new Error('Production worker version is missing')
  let script = original
  let tamper = false
  const precacheCookies: boolean[] = []
  const mime: Record<string, string> = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.woff2': 'font/woff2',
    '.png': 'image/png',
    '.webmanifest': 'application/manifest+json',
  }
  const server = createServer((request, response) => {
    void (async () => {
      const path = new URL(request.url ?? '/', 'http://127.0.0.1').pathname
      response.setHeader('Cache-Control', 'no-store')
      response.setHeader('Vary', 'Origin')
      if (path.startsWith('/assets/') && request.headers['sec-fetch-dest'] === 'empty')
        precacheCookies.push(Boolean(request.headers.cookie))
      if (path === '/sw.js') {
        response.setHeader('Content-Type', mime['.js']!)
        response.end(script)
      }
      else if (path.startsWith('/api/')) {
        response.writeHead(401, { 'Content-Type': 'application/json' })
        response.end(JSON.stringify({ code: 'auth.invalid_credentials', message: 'Unauthorized' }))
      }
      else if (path === '/private-document') {
        response.setHeader('Content-Type', mime['.html']!)
        response.end('<html><body>private-online-document</body></html>')
      }
      else {
        const relative = /\.[^/]+$/.test(path)
          ? path.slice(1)
          : 'index.html'
        const filename = resolve(dist, relative)
        if (!filename.startsWith(`${dist}${sep}`)) {
          response.writeHead(404).end()
          return
        }
        response.setHeader('Content-Type', mime[extname(filename)] ?? 'application/octet-stream')
        response.end(tamper && relative === 'index.html'
          ? '<html><body>unexpected private response</body></html>'
          : await readFile(filename))
      }
    })().catch(() => response.writeHead(404).end())
  })
  await new Promise<void>((ready, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', ready)
  })
  const address = server.address()
  if (!address || typeof address === 'string')
    throw new Error('Fixture server did not start')
  return {
    origin: `http://127.0.0.1:${address.port}`,
    version,
    precacheCookies,
    setUpdate(next: string, damaged: boolean) {
      script = original.replace(version, next)
      tamper = damaged
    },
    close: () => new Promise<void>((done, reject) => server.close(error => error
      ? reject(error)
      : done())),
  }
}

async function installUpdate(page: Page) {
  return page.evaluate(async () => {
    const registration = await navigator.serviceWorker.getRegistration()
    if (!registration)
      throw new Error('Service worker is not registered')
    const result = new Promise<string>((done) => {
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing
        if (!worker) {
          done('missing')
          return
        }
        const changed = () => {
          if (worker.state === 'installed' || worker.state === 'redundant')
            done(worker.state)
        }
        worker.addEventListener('statechange', changed)
        changed()
      }, { once: true })
    })
    await registration.update()
    return result
  })
}

test('real worker rejects altered shell bytes, waits for clients and cleans up only old versions', async ({ page, context }) => {
  const fixture = await updateFixture()
  const oldCache = `pandawords-shell-${fixture.version}`
  const badVersion = fixture.version === 'a'.repeat(20)
    ? 'c'.repeat(20)
    : 'a'.repeat(20)
  const nextVersion = fixture.version === 'b'.repeat(20)
    ? 'd'.repeat(20)
    : 'b'.repeat(20)
  const badCache = `pandawords-shell-${badVersion}`
  const nextCache = `pandawords-shell-${nextVersion}`
  try {
    await context.addCookies([{ name: 'precache-proof', value: 'test', url: fixture.origin }])
    await page.goto(`${fixture.origin}/login`)
    await expect(page.locator('#username')).toBeVisible()
    await page.evaluate(() => navigator.serviceWorker.ready)
    expect(fixture.precacheCookies.length).toBeGreaterThan(0)
    expect(fixture.precacheCookies).not.toContain(true)
    expect(await page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(false)
    await page.evaluate(() => caches.open('unrelated-app'))

    const controlled = await context.newPage()
    await controlled.goto(`${fixture.origin}/login`)
    await expect.poll(() => controlled.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true)
    await controlled.goto(`${fixture.origin}/private-document`)
    await expect(controlled.locator('body')).toHaveText('private-online-document')
    await controlled.goto(`${fixture.origin}/login`)
    const initialEntries = await page.evaluate(async (name) => {
      const cache = await caches.open(name)
      return (await cache.keys()).map(request => new URL(request.url).pathname)
    }, oldCache)
    expect(initialEntries).not.toContain('/private-document')

    fixture.setUpdate(badVersion, true)
    expect(await installUpdate(page)).toBe('redundant')
    const failedKeys = await page.evaluate(() => caches.keys())
    expect(failedKeys).toContain(oldCache)
    expect(failedKeys).not.toContain(badCache)
    expect(await controlled.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true)

    fixture.setUpdate(nextVersion, false)
    expect(await installUpdate(page)).toBe('installed')
    expect(await page.evaluate(async () => (await navigator.serviceWorker.getRegistration())?.waiting?.state)).toBe('installed')
    const waitingKeys = await page.evaluate(() => caches.keys())
    expect(waitingKeys).toContain(oldCache)
    expect(waitingKeys).toContain(nextCache)
    expect(await controlled.evaluate(async () => {
      const registration = await navigator.serviceWorker.getRegistration()
      return navigator.serviceWorker.controller === registration?.active
    })).toBe(true)

    await controlled.close()
    await expect.poll(() => page.evaluate(() => caches.keys())).not.toContain(oldCache)
    const activeKeys = await page.evaluate(() => caches.keys())
    expect(activeKeys).toContain(nextCache)
    expect(activeKeys).toContain('unrelated-app')
    expect(activeKeys).not.toContain(badCache)

    const fresh = await context.newPage()
    await fresh.goto(`${fixture.origin}/login`)
    await expect.poll(() => fresh.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true)
    await context.setOffline(true)
    await fresh.goto(`${fixture.origin}/projects/private-route`)
    await expect(fresh.locator('#username')).toBeVisible()
    await expect(fresh).toHaveURL(/\/login$/)
    const asset = initialEntries.find(path => path.startsWith('/assets/') && path.endsWith('.js'))!
    expect(await fresh.evaluate(async (path) => {
      try {
        await fetch(path, { headers: { Authorization: 'Bearer fixture' } })
        return 'unexpected-response'
      }
      catch {
        return 'network-unavailable'
      }
    }, asset)).toBe('network-unavailable')
  }
  finally {
    await context.setOffline(false)
    for (const openPage of context.pages())
      await openPage.close()
    await fixture.close()
  }
})
