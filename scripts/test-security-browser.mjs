import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'

const require = createRequire(new URL('../frontend/package.json', import.meta.url))
const { chromium } = require('@playwright/test')

const baseURL = process.env.PANDAWORDS_SECURITY_BASE_URL
const password = process.env.PANDAWORDS_SECURITY_PASSWORD
assert(baseURL && password, 'The isolated proxy URL and synthetic password are required.')

const image = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAGAAAABgCAIAAABt+uBvAAABNUlEQVR4nO3bQW6DMBRAwbjK/a/s7koXhpeERWgzs0VWpCeD8BcZc84b+74OriFQs4OCQEGgIFAQKAgUBAoCBYHCfe/CGLX031meSu2gIFAQKAgUBAoCBYGCQEGgIFAQKAgUBAoCBYGCQEGg9wQaf3DtkyPXnx+bz38fM8Z6fHnNtWObLi8Wu8WCQEGgIFAQKAgUBAoCBYGCQEGgIFAQKIy9w/qvM+6nWKa4v7bs2Bi73S+49ngruMWCQKFvsVMef5Bd9X99dlAQKAgUBAoCBYGCQO99D5oXfbt5nB0UBArGHRvjjjXjjlM8g4JAQaAgUBAoCBQECgIFgYJAQaAgUDDu2Bh3rBl3nOIZFAQKAgWBgkBBoCBQECg4asRRww4KAoXXv/v/EHZQECgIFAQKAgWBbse+AY3DUrjVhP21AAAAAElFTkSuQmCC',
  'base64',
)
const caddy = readFileSync(new URL('../deploy/Caddyfile.snippet', import.meta.url), 'utf8')
assert.match(caddy, /header Strict-Transport-Security "max-age=31536000"/)
assert.match(caddy, /reverse_proxy pandawords-web:80/)
assert.match(caddy, /header_up X-Panda-Client-IP \{remote_host\}/)

function assertHeaders(response) {
  const headers = response.headers
  assert.equal(headers.get('x-content-type-options'), 'nosniff')
  assert.equal(headers.get('x-frame-options'), 'DENY')
  assert.equal(headers.get('referrer-policy'), 'no-referrer')
  assert.equal(headers.get('permissions-policy'), 'camera=(), microphone=(), geolocation=()')
  const directives = Object.fromEntries(
    (headers.get('content-security-policy') ?? '').split(';')
      .map(value => value.trim().split(/\s+/))
      .filter(parts => parts.length > 1)
      .map(([name, ...values]) => [name, values]),
  )
  for (const [directive, values] of Object.entries({
    'default-src': ["'none'"],
    'script-src': ["'self'"],
    'style-src': ["'self'", "'unsafe-inline'"],
    'connect-src': ["'self'"],
    'img-src': ["'self'", 'blob:'],
    'media-src': ["'self'", 'blob:'],
    'font-src': ["'self'"],
    'object-src': ["'none'"],
    'base-uri': ["'none'"],
    'frame-ancestors': ["'none'"],
    'form-action': ["'self'"],
  }))
    assert.deepEqual(directives[directive], values, `Unexpected ${directive} policy.`)
  assert(!Object.values(directives).flat().includes('*'))
  assert(!Object.values(directives).flat().includes("'unsafe-eval'"))
}

const root = await fetch(`${baseURL}/`)
assert.equal(root.status, 200)
assertHeaders(root)
assert.equal(root.headers.get('cache-control'), 'no-cache')
assert.equal(root.headers.get('strict-transport-security'), null)
const shell = await root.text()
const asset = shell.match(/(?:src|href)="(\/assets\/[^"]+)"/)?.[1]
assert(asset, 'The production shell must reference a local fingerprinted asset.')
const staticAsset = await fetch(`${baseURL}${asset}`)
assert.equal(staticAsset.status, 200)
assertHeaders(staticAsset)
assert.match(staticAsset.headers.get('cache-control') ?? '', /immutable/)
for (const [path, status] of [
  ['/assets/not-present-abcdefgh.js', 404],
  ['/_media/image/forbidden.png', 404],
  ['/api/healthz', 200],
  ['/api/projects', 401],
  ['/reading/deep-link', 200],
]) {
  const response = await fetch(`${baseURL}${path}`)
  assert.equal(response.status, status, path)
  assertHeaders(response)
}
const redirect = await fetch(`${baseURL}/api/auth/login/`, {
  method: 'POST',
  body: '{}',
  headers: { 'Content-Type': 'application/json' },
  redirect: 'manual',
})
assert.equal(redirect.status, 307)
assert.match(redirect.headers.get('location') ?? '', /^https:\/\//)
assertHeaders(redirect)

async function json(response, status, label) {
  assert.equal(response.status(), status, `${label} returned an unexpected status.`)
  return response.json()
}

async function fillSecret(locator, value) {
  await locator.evaluate((element, input) => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(element, input)
    element.dispatchEvent(new Event('input', { bubbles: true }))
    element.dispatchEvent(new Event('change', { bubbles: true }))
  }, value)
}

const browser = await chromium.launch({ headless: true })
try {
  for (const [locale, title] of [['en', 'Projects'], ['zh-CN', '项目']]) {
    const violations = []
    const context = await browser.newContext({ baseURL })
    await context.exposeBinding('__reportSecurityViolation', (_source, directive) => {
      violations.push(directive)
    })
    await context.addInitScript((selectedLocale) => {
      localStorage.setItem(
        'pandawords.preferences',
        JSON.stringify({ theme: 'system', locale: selectedLocale }),
      )
      document.addEventListener('securitypolicyviolation', event => {
        globalThis.__reportSecurityViolation(event.effectiveDirective)
      })
    }, locale)
    const page = await context.newPage()
    await page.goto('/login')
    await fillSecret(page.locator('#username'), 'securityfixture')
    await fillSecret(page.locator('#password'), password)
    const login = page.waitForResponse(response =>
      response.url().endsWith('/api/auth/login') && response.request().method() === 'POST',
    )
    await page.locator('form button[type="submit"]').click()
    const auth = await json(await login, 200, 'Login')
    await page.waitForURL('**/projects')
    await page.getByRole('heading', { name: title, exact: true }).waitFor()
    const headers = { Authorization: `Bearer ${auth.access_token}` }
    const project = await json(await page.request.post('/api/projects', {
      headers,
      data: { name: `security-${randomUUID()}` },
    }), 201, 'Project creation')
    const candidates = await json(await page.request.post('/api/dictionary/candidates', {
      headers,
      data: { text: 'cat' },
    }), 200, 'Dictionary candidates')
    const candidate = candidates.candidates[0]
    const sense = candidate?.lexemes[0]?.senses[0]
    assert(sense, 'The offline fixture must contain a cat sense.')
    const added = await json(await page.request.post(`/api/projects/${project.id}/dictionary`, {
      headers,
      data: { lemma_key: candidate.lemma.id, selected_senses: [sense.id] },
    }), 200, 'Dictionary add')
    const senseId = added.selected_sense_ids[0]
    const upload = await json(await page.request.post(`/api/images/senses/${senseId}`, {
      headers: { ...headers, 'Content-Type': 'image/png', 'request-id': randomUUID() },
      data: image,
    }), 200, 'Image upload')
    const unauthorized = await page.request.get(`/api/media/${upload.id}`)
    assert.equal(unauthorized.status(), 401)
    const delivery = await page.request.get(`/api/media/${upload.id}`, { headers })
    assert.equal(delivery.status(), 200)
    assert.equal(delivery.headers()['cache-control'], 'private, no-store')
    assert.deepEqual(await delivery.body(), image)

    await page.goto(`/words/${added.lemma_id}`)
    const displayed = page.locator(`[data-sense-id="${senseId}"] [data-testid="sense-images"] img`).last()
    await displayed.waitFor({ state: 'visible' })
    assert.match(await displayed.getAttribute('src'), /^blob:/)
    assert.equal(await displayed.evaluate(element => element.naturalWidth), 96)
    await page.goto('/words')
    await page.getByTestId('graph-explorer').getByRole('button', { name: 'cat', exact: true }).click()
    await page.getByTestId('graph-canvas').waitFor({ state: 'visible' })
    await page.goto('/reading')
    await page.getByRole('heading', { name: locale === 'en' ? 'Reading' : '阅读', exact: true }).waitFor()
    await page.waitForTimeout(100)
    assert.deepEqual(violations, [], `A required ${locale} flow violated CSP.`)

    const executed = await page.evaluate(() => {
      globalThis.__unexpectedInlineScript = false
      const element = document.createElement('script')
      element.textContent = 'globalThis.__unexpectedInlineScript = true'
      document.head.append(element)
      return globalThis.__unexpectedInlineScript
    })
    assert.equal(executed, false)
    const connected = await page.evaluate(async () => {
      try {
        await fetch('https://example.invalid/', { credentials: 'omit' })
        return true
      }
      catch {
        return false
      }
    })
    assert.equal(connected, false)
    await page.waitForTimeout(100)
    assert(violations.some(value => value.startsWith('script-src')))
    assert(violations.includes('connect-src'))
    await context.close()
    console.log(`Production nginx browser flows and CSP enforcement: ${locale} passed.`)
  }
}
finally {
  await browser.close()
}
console.log('Production nginx headers, caching, proxy errors and protected media passed.')
