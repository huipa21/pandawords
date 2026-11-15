import { afterEach, expect, it, vi } from 'vitest'
import { registerServiceWorker } from './register'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

it('does not register in development or when service workers are unavailable', () => {
  const register = vi.fn()
  vi.stubGlobal('navigator', {
    serviceWorker: { register },
  })
  vi.stubEnv('PROD', false)
  registerServiceWorker()
  expect(register).not.toHaveBeenCalled()
  vi.stubEnv('PROD', true)
  vi.stubGlobal('navigator', {})
  expect(registerServiceWorker).not.toThrow()
})

it('registers once after load without caching worker updates', () => {
  const register = vi.fn().mockResolvedValue({})
  vi.stubGlobal('navigator', {
    serviceWorker: { register },
  })
  vi.stubEnv('PROD', true)
  vi.spyOn(document, 'readyState', 'get').mockReturnValue('loading')
  registerServiceWorker()
  expect(register).not.toHaveBeenCalled()
  window.dispatchEvent(new Event('load'))
  window.dispatchEvent(new Event('load'))
  expect(register).toHaveBeenCalledExactlyOnceWith('/sw.js', { updateViaCache: 'none' })
})

it('keeps the app usable if registration throws or rejects', async () => {
  const register = vi.fn().mockImplementationOnce(() => {
    throw new Error('restricted')
  }).mockRejectedValueOnce(new Error('offline'))
  vi.stubGlobal('navigator', {
    serviceWorker: { register },
  })
  vi.stubEnv('PROD', true)
  vi.spyOn(document, 'readyState', 'get').mockReturnValue('complete')
  expect(registerServiceWorker).not.toThrow()
  expect(registerServiceWorker).not.toThrow()
  await Promise.resolve()
  expect(register).toHaveBeenCalledTimes(2)
})
