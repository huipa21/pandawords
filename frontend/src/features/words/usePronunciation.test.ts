import { flushPromises, mount } from '@vue/test-utils'
import { NMessageProvider } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { createApiClient } from '@/api/client'
import { createAppI18n } from '@/i18n'
import { usePronunciation } from './usePronunciation'

const get = vi.hoisted(() => vi.fn())
vi.mock('@/api/client', async (original) => {
  const module = await original<typeof import('@/api/client')>()
  return {
    ...module,
    api: { GET: get },
  }
})
const play = vi.fn()
const pause = vi.fn()
const createUrl = vi.fn(() => 'blob:authenticated-pronunciation')
const revokeUrl = vi.fn()
let cleanup: (() => void) | undefined
let audio: { src: string, play: typeof play, pause: typeof pause }

function setup() {
  const id = ref('lemma:one')
  let playback!: ReturnType<typeof usePronunciation>
  const child = defineComponent({
    setup() {
      playback = usePronunciation(() => id.value)
      return () => h('p', 'Audio test')
    },
  })
  const i18n = createAppI18n()
  i18n.global.locale.value = 'en'
  const wrapper = mount(defineComponent({
    setup: () => () => h(NMessageProvider, null, {
      default: () => h(child),
    }),
  }), {
    attachTo: document.body,
    global: {
      plugins: [
        i18n,
      ],
    },
  })
  cleanup = () => wrapper.unmount()
  return { playback, id, wrapper }
}
beforeEach(() => {
  vi.clearAllMocks()
  play.mockResolvedValue(undefined)
  audio = { src: '', play, pause }
  vi.stubGlobal('Audio', class {
    constructor() {
      return audio
    }
  })
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = createUrl
    static revokeObjectURL = revokeUrl
  })
})
afterEach(() => {
  cleanup?.()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('authenticated pronunciation playback', () => {
  it('fetches opaque media through bearer client as a blob, never using the protected endpoint as audio src, and revokes on navigation/unmount', async () => {
    const transport = vi.fn<typeof fetch>(async () => new Response(new Blob(['audio'], { type: 'audio/mpeg' })))
    const client = createApiClient({
      baseUrl: 'https://pandawords.test',
      fetch: transport,
      auth: {
        getAccessToken: () => 'private-token',
        refresh: async () => null,
        logout: () => {},
      },
    })
    get.mockImplementation(client.GET)
    const { playback, id } = setup()
    await playback.play('media:opaque')
    const request = new Request(transport.mock.calls[0]![0])
    expect(request.headers.get('Authorization')).toBe('Bearer private-token')
    expect(request.credentials).toBe('include')
    expect(new URL(request.url).pathname).toContain('/api/media/')
    expect(get.mock.calls[0]![1]).toMatchObject({
      params: {
        path: { rid: 'media:opaque' },
      },
      parseAs: 'blob',
    })
    expect(play).toHaveBeenCalled()
    expect(audio.src).toBe('blob:authenticated-pronunciation')
    expect(createUrl).toHaveBeenCalledWith(expect.any(Blob))
    id.value = 'lemma:two'
    await flushPromises()
    expect(pause).toHaveBeenCalled()
    expect(revokeUrl).toHaveBeenCalledWith('blob:authenticated-pronunciation')
    await playback.play('media:two')
    cleanup?.()
    cleanup = undefined
    expect(revokeUrl).toHaveBeenCalledTimes(2)
  })

  it('reports fetch, empty media and playback failures explicitly', async () => {
    const { playback } = setup()
    get.mockRejectedValueOnce(new Error('offline'))
    await playback.play('media:one')
    expect(document.body.textContent).toContain('Audio could not be played.')
    get.mockResolvedValueOnce({
      response: new Response(null, { status: 403 }),
      error: { code: 'auth.forbidden' },
    })
    await playback.play('media:one')
    expect(document.body.textContent).toContain('You do not have permission')
    get.mockResolvedValueOnce({
      response: new Response(null, { status: 404 }),
      error: { code: 'media.not_found' },
    })
    await playback.play('media:one')
    expect(document.body.textContent).toContain('No pronunciation audio is available.')
    get.mockResolvedValueOnce({
      data: new Blob(),
      response: new Response(),
    })
    await playback.play('media:one')
    expect(createUrl).not.toHaveBeenCalled()
    get.mockResolvedValueOnce({
      data: new Blob(['audio']),
      response: new Response(),
    })
    play.mockRejectedValueOnce(new Error('unsupported'))
    await playback.play('media:one')
    expect(document.body.textContent).toContain('Audio could not be played.')
  })

  it('aborts navigation-disposed requests and never creates URLs for their late results', async () => {
    let resolve!: (value: unknown) => void
    get.mockReturnValueOnce(new Promise(done => resolve = done))
    const { playback, id } = setup()
    const pending = playback.play('media:one')
    const signal: AbortSignal = get.mock.calls[0]![1].signal
    expect(playback.loading.value).toBe(true)
    id.value = 'lemma:two'
    await flushPromises()
    expect(signal.aborted).toBe(true)
    resolve({
      data: new Blob(['audio']),
      response: new Response(),
    })
    await pending
    expect(createUrl).not.toHaveBeenCalled()
    expect(playback.loading.value).toBe(false)
  })

  it('cancels a pending request when the same pronunciation is toggled off', async () => {
    let resolve!: (value: unknown) => void
    get.mockReturnValueOnce(new Promise(done => resolve = done))
    const { playback } = setup()
    const pending = playback.play('media:one')
    const signal: AbortSignal = get.mock.calls[0]![1].signal
    await playback.play('media:one')
    expect(signal.aborted).toBe(true)
    resolve({
      data: new Blob(['audio']),
      response: new Response(),
    })
    await pending
    expect(createUrl).not.toHaveBeenCalled()
  })
})
