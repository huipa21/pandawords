import { useI18n } from 'vue-i18n'
import { normalizeApiError } from '@/api/errors'

/** Mirrors the server default `BUNDLE_IMPORT_MAX_BYTES`; the server still enforces its own bound. */
export const MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
const ARCHIVE_NAME = /\.(?:tar\.gz|tgz)$/i

export type ArchiveProblem = 'empty' | 'extension' | 'tooLarge'

/** Cheap client-side pre-check; the server validates format, content and size again. */
export function checkArchive(file: File): ArchiveProblem | null {
  if (!ARCHIVE_NAME.test(file.name))
    return 'extension'
  if (file.size === 0)
    return 'empty'
  if (file.size > MAX_ARCHIVE_BYTES)
    return 'tooLarge'
  return null
}

export function formatBytes(bytes: number) {
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit++
  }
  return `${unit
    ? value.toFixed(1)
    : value} ${units[unit]}`
}

/** Only the final path segment of a server-suggested name is used. */
export function downloadName(response: Response, fallback: string) {
  const header = response.headers.get('Content-Disposition') ?? ''
  const encoded = /filename\*=utf-8''([^;]+)/i.exec(header)?.[1]
  let name = /filename="?([^";]+)"?/i.exec(header)?.[1]
  if (encoded) {
    try {
      name = decodeURIComponent(encoded)
    }
    catch {}
  }
  const safe = name?.split(/[\\/]/).pop()?.trim()
  return safe || fallback
}

/** Saves an authenticated response body without exposing a reusable URL. */
export function saveBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.rel = 'noopener'
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 0)
}

export function skippedMedia(response: Response) {
  const value = Number(response.headers.get('X-PandaWords-Skipped-Media') ?? 0)
  return Number.isFinite(value) && value > 0
    ? value
    : 0
}

export function isAbort(error: unknown) {
  return error instanceof DOMException && error.name === 'AbortError'
}

export interface TransferError {
  text: string
  stage: string
  problems: string[]
}

export function useTransferErrors() {
  const { t, te } = useI18n()
  return (error: unknown, status: number): TransferError => {
    const normalized = normalizeApiError(error, status)
    const reason = normalized.code.replace(/^bundle\./, '').replaceAll('.', '_')
    const keys = [
      `portability.errors.${reason}`,
      `errors.${normalized.code.replaceAll('.', '_')}`,
      ...(normalized.code.startsWith('bundle.')
        ? ['portability.errors.rejected']
        : []),
    ]
    const key = keys.find(candidate => te(candidate)) ?? 'errors.generic'
    const stage = normalized.stage && te(`portability.stages.${normalized.stage}`)
      ? t(`portability.stages.${normalized.stage}`)
      : ''
    return {
      text: t(key),
      stage,
      problems: normalized.problems ?? [],
    }
  }
}
