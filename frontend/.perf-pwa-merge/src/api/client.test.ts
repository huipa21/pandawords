import { describe, expect, it, vi } from 'vitest'
import { createApiClient, readApiError } from './client'

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

function authLifecycle(refresh: () => Promise<string | null>) {
  return {
    getAccessToken: () => 'old-token',
    refresh: vi.fn(refresh),
    logout: vi.fn(),
  }
}

function clientWith(fetch: typeof globalThis.fetch, auth = authLifecycle(async () => 'new-token')) {
  return createApiClient({ baseUrl: 'https://pandawords.test', fetch, auth })
}

describe('aPI authentication lifecycle', () => {
  it('attaches the access token and shares one refresh across concurrent 401s', async () => {
    const refreshed = deferred<string | null>()
    const initialRequests = deferred<void>()
    const tokens: (string | null)[] = []
    const auth = authLifecycle(() => refreshed.promise)
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const request = new Request(input, init)
      const token = request.headers.get('Authorization')
      tokens.push(token)
      if (token === 'Bearer old-token') {
        if (tokens.length === 2)
          initialRequests.resolve()
        return new Response(null, { status: 401 })
      }
      return Response.json({ status: 'ok' })
    })
    const client = clientWith(fetch, auth)
    const pending = Promise.all([
      client.GET('/api/healthz'),
      client.GET('/api/readyz'),
    ])
    await initialRequests.promise
    refreshed.resolve('new-token')
    const results = await pending

    expect(auth.refresh).toHaveBeenCalledTimes(1)
    expect(auth.logout).not.toHaveBeenCalled()
    expect(tokens).toEqual([
      'Bearer old-token',
      'Bearer old-token',
      'Bearer new-token',
      'Bearer new-token',
    ])
    expect(results.map(result => result.data)).toEqual([
      { status: 'ok' },
      { status: 'ok' },
    ])
  })

  it('reuses completed refresh for a late 401 from the same old token', async () => {
    const lateResponse = deferred<Response>()
    let oldRequests = 0
    const auth = authLifecycle(async () => 'new-token')
    const fetch = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      if (new Request(input, init).headers.get('Authorization') === 'Bearer old-token') {
        oldRequests++
        return oldRequests === 1
          ? new Response(null, { status: 401 })
          : lateResponse.promise
      }
      return Response.json({ status: 'ok' })
    })
    const client = clientWith(fetch, auth)
    const first = client.GET('/api/healthz')
    const second = client.GET('/api/readyz')
    await first
    lateResponse.resolve(new Response(null, { status: 401 }))
    await second

    expect(auth.refresh).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(4)
  })

  it.each(['rejected', 'empty'])('logs out once when shared refresh is %s', async (failure) => {
    const refreshed = deferred<string | null>()
    const auth = authLifecycle(async () => {
      await refreshed.promise
      if (failure === 'rejected')
        throw new Error('Refresh unavailable')
      return null
    })
    const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json({
      code: 'auth.expired',
      message: 'Session expired.',
    }, { status: 401 }))
    const client = clientWith(fetch, auth)
    const requests = Promise.all([
      client.GET('/api/healthz'),
      client.GET('/api/readyz'),
    ])
    await vi.waitFor(() => expect(auth.refresh).toHaveBeenCalledTimes(1))
    refreshed.resolve(null)
    const results = await requests

    expect(auth.refresh).toHaveBeenCalledTimes(1)
    expect(auth.logout).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(results[0]!.error).toEqual({
      code: 'auth.expired',
      message: 'Session expired.',
      field: null,
    })
  })

  it('does not refresh or retry again when the retry also returns 401', async () => {
    const auth = authLifecycle(async () => 'new-token')
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 401 }))
    const result = await clientWith(fetch, auth).GET('/api/healthz')
    expect(result.response.status).toBe(401)
    expect(auth.refresh).toHaveBeenCalledTimes(1)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('supports public clients and explicitly excluded auth requests', async () => {
    const auth = authLifecycle(async () => 'new-token')
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 401 }))
    const options = { baseUrl: 'https://pandawords.test', fetch }
    await createApiClient(options).GET('/api/healthz')
    await createApiClient({
      ...options,
      auth,
      shouldRefresh: () => false,
    }).GET('/api/healthz')
    expect(auth.refresh).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(new Request(fetch.mock.calls[0]![0]).headers.has('Authorization')).toBe(false)
  })

  it('excludes auth endpoints from recovery even on the shared authenticated client', async () => {
    const auth = authLifecycle(async () => 'new-token')
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(null, { status: 401 }))
    const client = clientWith(fetch, auth)
    await client.POST('/api/auth/login', {
      body: { username: 'user', password: 'password' },
    })
    await client.POST('/api/auth/refresh')
    await client.POST('/api/auth/logout')
    await client.POST('/api/auth/password', {
      body: { current_password: 'old', new_password: 'new' },
    })
    expect(auth.refresh).not.toHaveBeenCalled()
    expect(auth.logout).not.toHaveBeenCalled()
    expect(fetch).toHaveBeenCalledTimes(4)
  })
})

describe('aPI error normalization', () => {
  it('preserves backend error codes, messages and validation fields', async () => {
    const error = { code: 'validation.invalid', message: 'Invalid input.', field: 'name' }
    const fetch = vi.fn<typeof globalThis.fetch>(async () => Response.json(error, { status: 422 }))
    const result = await clientWith(fetch).GET('/api/healthz')
    expect(result.error).toEqual(error)
  })

  it.each(['not JSON', '{"code":1,"message":false,"field":{}}'])(
    'normalizes malformed errors without leaking response text: %s',
    async (body) => {
      expect(await readApiError(new Response(body, { status: 502, statusText: 'Bad Gateway' })))
        .toEqual({ code: 'http.502', message: 'Bad Gateway', field: null })
    },
  )
})
