import type { components } from '@/api/schema'

export type PendingReview
  = | { action: 'answer', body: components['schemas']['AttemptAnswer'] }
    | { action: 'giveup', body: components['schemas']['AttemptGiveUp'] }
    | { action: 'confirm', body: components['schemas']['AttemptConfirm'] }

export interface ReviewSession {
  attemptId?: string
  pending?: PendingReview
  completed: string[]
}

export function reviewSessionKey(owner: string, project: string) {
  return `pandawords.review:${encodeURIComponent(owner)}:${encodeURIComponent(project)}`
}

export function readReviewSession(key: string): ReviewSession {
  const raw = sessionStorage.getItem(key)
  if (!raw)
    return { completed: [] }
  const value = JSON.parse(raw) as ReviewSession
  if (!Array.isArray(value.completed) || !value.completed.every(id => typeof id === 'string')
    || (value.attemptId !== undefined && typeof value.attemptId !== 'string')) {
    throw new Error('Invalid review session')
  }
  if (value.pending) {
    const { action, body } = value.pending
    if (!value.attemptId || !body
      || (action === 'answer' && (typeof body.answer !== 'string' || !Number.isInteger(body.duration_ms) || body.duration_ms < 0))
      || (action === 'giveup' && (!Number.isInteger(body.duration_ms) || body.duration_ms < 0))
      || (action === 'confirm' && ![1, 2, 3, 4].includes(body.rating))
      || !['answer', 'giveup', 'confirm'].includes(action)) {
      throw new Error('Invalid pending review')
    }
  }
  return value
}

export function writeReviewSession(key: string, value: ReviewSession) {
  sessionStorage.setItem(key, JSON.stringify(value))
}
