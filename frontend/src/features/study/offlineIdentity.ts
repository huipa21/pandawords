let owner = ''
export const offlineEvents = new EventTarget()
export const offlineOwner = () => owner
export function activateOfflineOwner(value: string) {
  owner = value
}
export function revokeOfflineOwner(value: string) {
  if (owner === value) {
    owner = ''
    offlineEvents.dispatchEvent(new Event('purged'))
  }
}
