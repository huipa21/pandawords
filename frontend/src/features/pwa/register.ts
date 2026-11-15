function warnRegistrationFailure() {
  console.warn('pwa_service_worker_registration_failed')
}

export function registerServiceWorker() {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator))
    return
  const register = () => {
    try {
      void navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(warnRegistrationFailure)
    }
    catch {
      warnRegistrationFailure()
    }
  }
  if (document.readyState === 'complete')
    register()
  else
    window.addEventListener('load', register, { once: true })
}
