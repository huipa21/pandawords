export function registerServiceWorker() {
  if (!import.meta.env.PROD || !('serviceWorker' in navigator))
    return
  const register = () => {
    try {
      void navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' }).catch(() => {})
    }
    catch {
      // Registration is optional, including when browser storage is restricted.
    }
  }
  if (document.readyState === 'complete')
    register()
  else
    window.addEventListener('load', register, { once: true })
}
