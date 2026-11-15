import type { components } from '@/api/schema'
import { offlineOwner, revokeOfflineOwner } from './offlineIdentity'

export { activateOfflineOwner, offlineEvents } from './offlineIdentity'

type Open = components['schemas']['AttemptOpen']
export type OfflineAttempt = Pick<Open, 'id' | 'project_id' | 'prompt' | 'exercise' | 'issued_at' | 'expires_at'>
export interface OfflineEntry {
  attempt: OfflineAttempt
  answer?: { answer: string, duration_ms: number, client_key: string, gave_up?: boolean }
  rating?: components['schemas']['AttemptConfirm']['rating']
  failure?: 'failed' | 'expired' | 'stale'
}
export interface OfflineData {
  entries: OfflineEntry[]
  receipts: string[]
}
let channel: BroadcastChannel | undefined

function connect() {
  if (!channel && typeof BroadcastChannel !== 'undefined') {
    channel = new BroadcastChannel('pandawords-offline-review')
    channel.onmessage = ({ data }: MessageEvent<unknown>) => {
      if (typeof data === 'string')
        revokeOfflineOwner(data)
    }
  }
}

function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('pandawords-offline-review-v1', 1)
    request.onupgradeneeded = () => request.result.createObjectStore('owners')
    request.onsuccess = () => {
      request.result.onversionchange = () => request.result.close()
      resolve(request.result)
    }
    request.onerror = () => reject(request.error)
    request.onblocked = () => reject(new Error('Offline database blocked'))
  })
}

export async function clearOfflineOwner(owner: string) {
  revokeOfflineOwner(owner)
  connect()
  channel?.postMessage(owner)
  const db = await database()
  try {
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction('owners', 'readwrite')
      tx.objectStore('owners').delete(owner)
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error ?? new Error('Offline deletion aborted'))
    })
  }
  finally {
    db.close()
  }
}

export async function offlineData(owner: string, change?: (data: OfflineData) => void): Promise<OfflineData> {
  connect()
  const db = await database()
  try {
    return await new Promise<OfflineData>((resolve, reject) => {
      const tx = db.transaction('owners', change ? 'readwrite' : 'readonly')
      const store = tx.objectStore('owners')
      const request = store.get(owner)
      let data: OfflineData
      tx.oncomplete = () => resolve(data)
      tx.onerror = () => reject(tx.error)
      tx.onabort = () => reject(tx.error ?? new Error('Offline transaction aborted'))
      request.onsuccess = () => {
        if (offlineOwner() !== owner) {
          tx.abort()
          return
        }
        data = request.result ?? { entries: [], receipts: [] }
        if (!Array.isArray(data.entries) || !Array.isArray(data.receipts) || data.entries.length > 20) {
          tx.abort()
          return
        }
        if (change) {
          try {
            change(data)
            if (data.entries.length > 20)
              throw new Error('Offline queue full')
            store.put(data, owner)
          }
          catch {
            tx.abort()
          }
        }
      }
    })
  }
  finally {
    db.close()
  }
}

export function minimalAttempt(attempt: Open): OfflineAttempt {
  return {
    id: attempt.id,
    project_id: attempt.project_id,
    exercise: attempt.exercise,
    issued_at: attempt.issued_at,
    expires_at: attempt.expires_at,
    prompt: {
      text: attempt.prompt.text,
      input: attempt.prompt.input,
      choices: attempt.prompt.choices?.map(choice => ({ id: choice.id, label: choice.label })) ?? [],
    },
  }
}
