import type { components } from '@/api/schema'
import { api } from '@/api/client'

export type ImportSummary = components['schemas']['ImportSummary']
export type RestoreSummary = components['schemas']['RestoreSummary']

// The generated body type is `string`; a File is streamed as the raw gzip body instead.
function rawArchive(file: File) {
  return {
    body: file as unknown as string,
    bodySerializer: (body: string) => body,
    headers: { 'Content-Type': 'application/gzip' },
  }
}

export function exportProject(id: string, signal: AbortSignal) {
  return api.GET('/api/projects/{id}/export', {
    params: {
      path: { id },
    },
    parseAs: 'blob',
    signal,
  })
}

export function importProject(file: File, includeProgress: boolean | undefined, signal: AbortSignal) {
  return api.POST('/api/projects/import', {
    params: {
      query: includeProgress === undefined
        ? {}
        : { include_progress: includeProgress },
    },
    ...rawArchive(file),
    signal,
  })
}

export function downloadUserBackup(signal: AbortSignal) {
  return api.GET('/api/me/backup', { parseAs: 'blob', signal })
}

export function restoreUserBackup(file: File, includeProgress: boolean | undefined, signal: AbortSignal) {
  return api.POST('/api/me/restore', {
    params: {
      query: { include_progress: includeProgress ?? true },
    },
    ...rawArchive(file),
    signal,
  })
}
