// @vitest-environment node
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { runInNewContext } from 'node:vm'
import { describe, expect, it, vi } from 'vitest'

const origin = 'https://pandawords.test'
const source = readFileSync(new URL('../../../pwa/worker.js', import.meta.url), 'utf8')
const paths = ['/index.html', '/assets/app-hash1234.js', '/manifest.v1.webmanifest']
const integrity = `sha256-${createHash('sha256').update('public shell').digest('base64')}`
const precache = paths.map(url => ({ url, integrity }))

function harness(version = 'one', stores = new Map<string, Map<string, Response>>()) {
  const handlers = new Map<string, (event: unknown) => void>()
  const fetch = vi.fn(async (_request: unknown): Promise<Response> => new Response('public shell'))
  const caches = {
    keys: async () => [
      ...stores.keys(),
    ],
    delete: vi.fn(async (key: string) => stores.delete(key)),
    open: async (name: string) => {
      if (!stores.has(name))
        stores.set(name, new Map())
      const entries = stores.get(name)!
      const key = (request: string | Request) => new URL(
        typeof request === 'string'
          ? request
          : request.url,
        origin,
      ).href
      return {
        addAll: async (requests: Request[]) => {
          const responses = await Promise.all(requests.map(async (request) => {
            const response = await fetch(request)
            if (!response.ok)
              throw new Error('install failed')
            return response
          }))
          requests.forEach((request, index) => {
            const response = responses[index]!
            entries.set(key(request), response)
          })
        },
        match: async (request: string | Request) => entries.get(key(request))?.clone(),
      }
    },
  }
  class AbsoluteRequest extends Request {
    constructor(path: string, init?: RequestInit) {
      super(new URL(path, origin), init)
    }
  }
  const self = {
    location: { origin },
    addEventListener: (type: string, handler: (event: unknown) => void) => handlers.set(type, handler),
    skipWaiting: vi.fn(),
    clients: {
      claim: vi.fn(),
    },
  }
  runInNewContext(source.replace('__PW_VERSION__', version).replace('__PW_PRECACHE__', JSON.stringify(precache)), {
    ...self,
    caches,
    fetch,
    Request: AbsoluteRequest,
    URL,
  })
  async function lifecycle(type: string) {
    let result: Promise<void> | undefined
    handlers.get(type)!({
      waitUntil: (promise: Promise<void>) => result = promise,
    })
    await result
  }
  function request(path: string, init: { mode?: string, method?: string, headers?: HeadersInit } = {}) {
    let result: Promise<Response> | undefined
    handlers.get('fetch')!({
      request: {
        url: new URL(path, origin).href,
        mode: 'cors',
        method: 'GET',
        ...init,
        headers: new Headers(init.headers),
      },
      respondWith: (promise: Promise<Response>) => result = promise,
    })
    return result
  }
  return {
    lifecycle,
    request,
    stores,
    fetch,
    self,
  }
}

describe('static-only service worker', () => {
  it('installs credential-free public files, waits safely, and cleans only its old caches on activation', async () => {
    const old = harness()
    await old.lifecycle('install')
    old.stores.set('unrelated-app', new Map())
    const next = harness('two', old.stores)
    await next.lifecycle('install')
    expect([
      ...next.stores.keys(),
    ]).toContain('pandawords-shell-one')
    for (const [request] of next.fetch.mock.calls) {
      expect(request).toMatchObject({
        credentials: 'omit',
        cache: 'reload',
        redirect: 'error',
        integrity,
      })
    }
    expect(next.self.skipWaiting).not.toHaveBeenCalled()
    await next.lifecycle('activate')
    expect([
      ...next.stores.keys(),
    ]).toEqual(['unrelated-app', 'pandawords-shell-two'])
    expect(next.self.clients.claim).not.toHaveBeenCalled()
  })

  it('removes a failed new install without deleting the working shell', async () => {
    const old = harness()
    await old.lifecycle('install')
    const next = harness('two', old.stores)
    next.fetch.mockResolvedValueOnce(new Response('one static file'))
      .mockRejectedValueOnce(new Error('offline'))
    await expect(next.lifecycle('install')).rejects.toThrow('offline')
    expect([
      ...next.stores.keys(),
    ]).toEqual(['pandawords-shell-one'])
  })

  it('does not delete an existing cache when a reinstall of the same version fails', async () => {
    const old = harness()
    await old.lifecycle('install')
    const retry = harness('one', old.stores)
    retry.fetch.mockRejectedValueOnce(new Error('offline'))
    await expect(retry.lifecycle('install')).rejects.toThrow('offline')
    expect([
      ...retry.stores.get('pandawords-shell-one')!.keys(),
    ]).toEqual(paths.map(path => `${origin}${path}`))
  })

  it('never intercepts API, media, authorization, foreign or non-GET traffic', async () => {
    const worker = harness()
    await worker.lifecycle('install')
    for (const path of [
      '/api',
      '/api/auth/me',
      '/api/media/private?token=secret',
      '/media/private',
      '/_media/private',
    ]) {
      expect(worker.request(path)).toBeUndefined()
      expect(worker.request(path, { mode: 'navigate' })).toBeUndefined()
    }
    expect(worker.request('/assets/app-hash1234.js', {
      headers: { authorization: 'Bearer private' },
    })).toBeUndefined()
    expect(worker.request('https://foreign.test/assets/app-hash1234.js')).toBeUndefined()
    expect(worker.request('/index.html', { method: 'POST' })).toBeUndefined()
    expect(worker.request('/assets/not-in-build.js')).toBeUndefined()
    expect(worker.request('/assets/app-hash1234.js?private=1')).toBeUndefined()
    expect(worker.fetch).toHaveBeenCalledTimes(paths.length)
  })

  it('uses the network online and the static shell offline without storing any private navigation or runtime result', async () => {
    const worker = harness()
    await worker.lifecycle('install')
    worker.fetch.mockResolvedValue(new Response('private online document'))
    expect(await (await worker.request('/projects/owner-secret', { mode: 'navigate' }))!.text()).toBe('private online document')
    worker.fetch.mockRejectedValue(new Error('offline'))
    for (const path of ['/', '/login', '/projects/owner-secret']) {
      expect(await (await worker.request(path, { mode: 'navigate' }))!.text()).toBe('public shell')
    }
    expect(await (await worker.request('/assets/app-hash1234.js'))!.text()).toBe('public shell')
    const entries = worker.stores.get('pandawords-shell-one')!
    expect([
      ...entries.keys(),
    ]).toEqual(paths.map(path => `${origin}${path}`))
    expect(await Promise.all([
      ...entries.values(),
    ].map(response => response.clone().text()))).not.toContain('private online document')
    entries.delete(`${origin}/assets/app-hash1234.js`)
    worker.fetch.mockResolvedValue(new Response('runtime asset'))
    await worker.request('/assets/app-hash1234.js')
    expect(entries.has(`${origin}/assets/app-hash1234.js`)).toBe(false)
  })
})
