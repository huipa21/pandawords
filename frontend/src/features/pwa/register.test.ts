import { afterEach, expect, it, vi } from 'vitest'
import { registerServiceWorker } from './register'

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllEnvs()
  vi.unstubAllGlobals()
})

it('does not register in development or when service workers are unavailable', () => {
  const register = vi.fn()
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.stubGlobal('navigator', {
    serviceWorker: { register },
  })
  vi.stubEnv('PROD', false)
  registerServiceWorker()
  expect(register).not.toHaveBeenCalled()
  vi.stubEnv('PROD', true)
  vi.stubGlobal('navigator', {})
  expect(registerServiceWorker).not.toThrow()
  expect(warning).not.toHaveBeenCalled()
})

it('registers once after load without caching worker updates', () => {
  const register = vi.fn().mockResolvedValue({})
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
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
  expect(warning).not.toHaveBeenCalled()
})

it('logs a safe warning and keeps the app usable if registration throws or rejects', async () => {
  const warning = vi.spyOn(console, 'warn').mockImplementation(() => {})
  const register = vi.fn().mockImplementationOnce(() => {
    throw new Error('sensitive synchronous registration details')
  }).mockRejectedValueOnce(new Error('sensitive asynchronous registration details'))
  vi.stubGlobal('navigator', {
    serviceWorker: { register },
  })
  vi.stubEnv('PROD', true)
  vi.spyOn(document, 'readyState', 'get').mockReturnValue('complete')
  expect(registerServiceWorker).not.toThrow()
  expect(registerServiceWorker).not.toThrow()
  await Promise.resolve()
  expect(register).toHaveBeenCalledTimes(2)
  expect(warning.mock.calls).toEqual([
    ['pwa_service_worker_registration_failed'],
    ['pwa_service_worker_registration_failed'],
  ])
})
