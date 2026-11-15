import type { paths } from './schema'
import createClient from 'openapi-fetch'
import { readApiError } from './errors'

export type { ApiError } from './errors'
export { readApiError } from './errors'

export interface AuthLifecycle {
  getAccessToken: () => string | null
  getSessionVersion?: () => number
  /** Store the new token in memory before resolving; avoid refresh recursion. */
  refresh: () => Promise<string | null>
  logout: () => void | Promise<void>
}

export interface ApiClientOptions {
  baseUrl?: string
  fetch?: typeof globalThis.fetch
  auth?: AuthLifecycle
  /** Additional exclusions from recovery beyond the built-in auth endpoint exclusions. */
  shouldRefresh?: (request: Request) => boolean
}

export function createApiClient(options: ApiClientOptions = {}) {
  const transport = options.fetch ?? globalThis.fetch.bind(globalThis)
  let refreshing: Promise<string | null> | undefined
  let generation = 0
  let refreshedToken: string | null = null

  function refresh(auth: AuthLifecycle) {
    const session = auth.getSessionVersion?.()
    refreshing ??= (async () => {
      try {
        const token = await auth.refresh()
        if (token)
          return token
      }
      catch {
        // A refresh rejection (including a network error) invalidates the session.
      }
      if (session === auth.getSessionVersion?.())
        await auth.logout()
      return null
    })().then((token) => {
      refreshedToken = token
      generation++
      return token
    }).finally(() => {
      refreshing = undefined
    })
    return refreshing
  }

  const authenticatedFetch: typeof globalThis.fetch = async (input, init) => {
    const request = new Request(input, init)
    const auth = options.auth
    const startedGeneration = generation
    const session = auth?.getSessionVersion?.()
    const token = auth?.getAccessToken()
    if (token)
      request.headers.set('Authorization', `Bearer ${token}`)

    // Keep an unconsumed copy so body-bearing requests can be retried once.
    const retry = request.clone()
    let response = await transport(request)
    const authEndpoint = /\/api\/auth\/(?:login|refresh|logout|password)$/.test(new URL(request.url).pathname)
    if (response.status === 401 && token && auth && !authEndpoint && (options.shouldRefresh?.(request) ?? true) && session === auth.getSessionVersion?.()) {
      // A late 401 from an older token shares the already-completed refresh too.
      const nextToken = startedGeneration === generation
        ? await refresh(auth)
        : refreshedToken
      if (nextToken && session === auth.getSessionVersion?.()) {
        retry.headers.set('Authorization', `Bearer ${nextToken}`)
        response = await transport(retry)
      }
    }
    if (response.ok)
      return response

    const error = await readApiError(response.clone())
    const headers = new Headers(response.headers)
    headers.set('Content-Type', 'application/json')
    headers.delete('Content-Length')
    headers.delete('Content-Encoding')
    return new Response(JSON.stringify(error), {
      status: response.status,
      statusText: response.statusText,
      headers,
    })
  }

  return createClient<paths>({ baseUrl: options.baseUrl ?? '', credentials: 'include', fetch: authenticatedFetch })
}

const appOptions: ApiClientOptions = {}
export const api = createApiClient(appOptions)

export function configureApiAuth(auth: AuthLifecycle) {
  appOptions.auth = auth
}
