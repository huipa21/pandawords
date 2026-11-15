import { expect, test } from '@playwright/test'

test('measure cold service-worker install responses', async ({ context, page, request }) => {
  const workerSource = await (await request.get('/sw.js')).text()
  const precache = JSON.parse(workerSource.match(/^const precache = (.+)$/m)![1]!) as { url: string }[]
  const expected = new Set(precache.map(entry => entry.url))
  const seen = new Map<string, { bytes: number, status: number, encoding: string | undefined }>()
  context.on('response', (response) => {
    if (response.request().serviceWorker()) {
      const url = new URL(response.url()).pathname
      if (!expected.has(url))
        return
      seen.set(url, {
        bytes: Number(response.headers()['content-length']),
        status: response.status(),
        encoding: response.headers()['content-encoding'],
      })
    }
  })
  await context.route('**/api/**', route => route.fulfill({ status: 401 }))
  await page.goto('/login')
  await page.evaluate(() => navigator.serviceWorker.ready)
  await expect.poll(() => seen.size).toBe(precache.length)
  expect([...seen.values()].every(result => result.status === 200)).toBe(true)
  const timing = await context.serviceWorkers()[0]!.evaluate(() => performance.getEntriesByType('resource').map((entry) => {
    const resource = entry as PerformanceResourceTiming
    return {
      url: new URL(resource.name).pathname,
      encoded: resource.encodedBodySize,
      decoded: resource.decodedBodySize,
      transfer: resource.transferSize,
    }
  }))
  const assets = timing.filter(entry => expected.has(entry.url))
  console.log(JSON.stringify({
    count: seen.size,
    timed: assets.length,
    encodedBytes: assets.reduce((sum, entry) => sum + entry.encoded, 0),
    decodedBytes: assets.reduce((sum, entry) => sum + entry.decoded, 0),
    transferBytes: assets.reduce((sum, entry) => sum + entry.transfer, 0),
    contentEncodings: [...new Set([...seen.values()].map(result => result.encoding ?? 'identity'))],
  }))
})
