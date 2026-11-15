/* global caches, fetch, Request, URL */
const cachePrefix = 'pandawords-shell-'
const cacheName = `${cachePrefix}__PW_VERSION__`
// eslint-disable-next-line no-undef -- Replaced by the production build.
const precache = __PW_PRECACHE__
const staticUrls = new Set(precache.map(({ url }) => new URL(url, globalThis.location.origin).href))

globalThis.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const existed = (await caches.keys()).includes(cacheName)
    try {
      const cache = await caches.open(cacheName)
      await cache.addAll(precache.map(({ url, integrity }) => new Request(url, {
        credentials: 'omit',
        cache: 'reload',
        redirect: 'error',
        integrity,
      })))
    }
    catch (error) {
      if (!existed)
        await caches.delete(cacheName)
      throw error
    }
  })())
})

// No skipWaiting/claim: an update must not replace the shell under an open review.
globalThis.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name.startsWith(cachePrefix) && name !== cacheName)
        await caches.delete(name)
    }
  })())
})

globalThis.addEventListener('fetch', (event) => {
  const request = event.request
  const url = new URL(request.url)
  if (request.method !== 'GET' || url.origin !== globalThis.location.origin
    || request.headers.has('authorization')
    || /^\/(?:api|media|_media)(?:\/|$)/i.test(url.pathname)) {
    return
  }

  if (request.mode === 'navigate') {
    event.respondWith((async () => {
      try {
        // Never store a navigation response, even for / or /login.
        return await fetch(request)
      }
      catch {
        const cache = await caches.open(cacheName)
        // The build verifies public bytes; request-specific Vary headers must not break offline use.
        const shell = await cache.match('/index.html', { ignoreVary: true })
        if (shell)
          return shell
        throw new Error('Static application shell unavailable')
      }
    })())
  }
  else if (staticUrls.has(url.href)) {
    event.respondWith((async () => {
      const cache = await caches.open(cacheName)
      return await cache.match(url.href, { ignoreVary: true }) || fetch(request)
    })())
  }
})
