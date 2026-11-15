import type { components } from '@/api/schema'
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { createApiClient } from '@/api/client'
import { normalizeApiError } from '@/api/errors'
import { AuthRequestError, transportError } from '@/features/auth/errors'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(null)
  const user = ref<components['schemas']['UserRead'] | null>(null)
  const sessionError = ref<string | null>(null)
  const isAdmin = computed(() => user.value?.role === 'admin')
  const client = createApiClient()
  let version = 0
  let restorePromise: Promise<void> | undefined
  let refreshPromise: Promise<string | null> | undefined
  let mutation: Promise<unknown> = Promise.resolve()
  let cookieAccessToken: string | null = null

  function reset() {
    version++
    accessToken.value = null
    user.value = null
    cookieAccessToken = null
  }

  function apply(data: components['schemas']['AuthRead']) {
    accessToken.value = data.access_token
    user.value = data.user
  }

  function refresh() {
    if (refreshPromise)
      return refreshPromise
    const started = version
    refreshPromise = (async () => {
      try {
        const result = await client.POST('/api/auth/refresh')
        // A stale response may still rotate the httpOnly cookie. Logout must revoke it
        // with its matching access token, without restoring the visible session.
        if (result.data)
          cookieAccessToken = result.data.access_token
        if (started !== version)
          return null
        if (!result.data) {
          const error = normalizeApiError(result.error, result.response.status)
          if (result.response.status !== 401)
            sessionError.value = error.code
          reset()
          return null
        }
        apply(result.data)
        return accessToken.value
      }
      catch {
        if (started === version) {
          sessionError.value = 'transport'
          reset()
        }
        return null
      }
    })().finally(() => {
      refreshPromise = undefined
    })
    return refreshPromise
  }

  function restore() {
    restorePromise ??= refresh().then(() => {})
    return restorePromise
  }

  // Cookie-changing mutations wait for old refreshes before replacing/clearing the cookie.
  function mutate<T>(operation: () => Promise<T>) {
    const pendingRefresh = refreshPromise
    const result = mutation.then(async () => {
      await pendingRefresh
      return operation()
    })
    mutation = result.catch(() => {})
    return result
  }

  function login(body: components['schemas']['LoginRequest']) {
    reset()
    sessionError.value = null
    const started = version
    return mutate(async () => {
      const result = await client.POST('/api/auth/login', { body }).catch(transportError)
      if (!result.data)
        throw new AuthRequestError(normalizeApiError(result.error, result.response.status))
      cookieAccessToken = result.data.access_token
      if (started === version)
        apply(result.data)
    })
  }

  function changePassword(body: components['schemas']['PasswordChange']) {
    const started = version
    const token = accessToken.value
    return mutate(async () => {
      const result = await client.POST('/api/auth/password', {
        body,
        headers: { Authorization: `Bearer ${token}` },
      }).catch(transportError)
      if (!result.data)
        throw new AuthRequestError(normalizeApiError(result.error, result.response.status))
      cookieAccessToken = result.data.access_token
      if (started === version) {
        version++
        apply(result.data)
      }
    })
  }

  function logout() {
    const token = accessToken.value
    reset()
    const started = version
    return mutate(async () => {
      const logoutToken = cookieAccessToken ?? token
      const revoke = (bearer: string | null) => client.POST('/api/auth/logout', {
        headers: bearer
          ? { Authorization: `Bearer ${bearer}` }
          : {},
      }).catch(transportError)
      let result = await revoke(logoutToken)
      if (result.response.status === 401) {
        // This transport has no lifecycle recovery. Keep rotated credentials local:
        // queued logins wait for revocation, and no stale result can restore auth.
        const refreshed = await client.POST('/api/auth/refresh').catch(transportError)
        if (!refreshed.data) {
          if (![401, 403].includes(refreshed.response.status))
            throw new AuthRequestError(normalizeApiError(refreshed.error, refreshed.response.status))
          if (started === version)
            cookieAccessToken = null
          return
        }
        result = await revoke(refreshed.data.access_token)
      }
      if (started === version)
        cookieAccessToken = null
      if (!result.response.ok)
        throw new AuthRequestError(normalizeApiError(result.error, result.response.status))
    })
  }

  return {
    accessToken,
    user,
    isAdmin,
    sessionError,
    getSessionVersion: () => version,
    restore,
    refresh,
    reset,
    login,
    changePassword,
    logout,
  }
})
