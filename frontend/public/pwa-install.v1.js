/* global window */
(() => {
  if (window.__pandawordsInstall)
    return

  const listeners = new Set()
  let pending
  let installed = false
  const notify = () => {
    for (const listener of listeners)
      listener({ event: pending, installed })
  }

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault()
    if (installed || typeof event.prompt !== 'function' || typeof event.userChoice?.then !== 'function')
      return
    pending = event
    notify()
  })

  window.addEventListener('appinstalled', () => {
    installed = true
    pending = undefined
    notify()
  })

  window.__pandawordsInstall = {
    subscribe(listener) {
      listeners.add(listener)
      listener({ event: pending, installed })
      return () => {
        listeners.delete(listener)
      }
    },
    clear(event) {
      if (!event || pending === event)
        pending = undefined
    },
  }
})()
