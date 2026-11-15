export interface InstallEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

interface InstallAvailability {
  event: InstallEvent | undefined
  installed: boolean
}

interface InstallBridge {
  subscribe: (listener: (availability: InstallAvailability) => void) => () => void
  clear: (event?: InstallEvent) => void
}

declare global {
  interface Window {
    __pandawordsInstall?: InstallBridge
  }
}

export function subscribeToInstallAvailability(listener: (availability: InstallAvailability) => void) {
  return window.__pandawordsInstall?.subscribe(listener) ?? (() => {})
}

export function clearInstallPrompt(event?: InstallEvent) {
  window.__pandawordsInstall?.clear(event)
}
