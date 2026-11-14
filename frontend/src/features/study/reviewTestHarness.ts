import type { components } from '@/api/schema'
import { plan, project } from './testHarness'

export { button, failure, project, setup, success } from './testHarness'

export const open: components['schemas']['AttemptOpen'] = {
  id: 'attempt:first',
  project_id: project.id,
  sense_id: 'sense:bank',
  exercise: 'def2word',
  kind: 'recognition',
  status: 'open',
  prompt: {
    text: 'A financial institution',
    input: 'choice',
    choices: [
      { id: 'opaque-bank', label: 'bank' },
      { id: 'opaque-tree', label: 'tree' },
    ],
  },
  issued_at: '2026-11-14T01:00:00Z',
  expires_at: '2099-11-14T02:00:00Z',
  hint_used: false,
  skipped: [],
}
export const graded: components['schemas']['AttemptGraded'] = {
  ...open,
  status: 'graded',
  feedback: { correct: true, answer: 'bank' },
  auto_rating: 3,
  duration_ms: 125,
  server_elapsed_ms: 250,
}
export const memory: components['schemas']['MemoryRead'] = {
  id: 'memory:bank',
  sense_id: open.sense_id,
  introduced: false,
  card: { card_id: 1, state: 1, due: open.issued_at },
}
export const confirmed: components['schemas']['AttemptConfirmed'] = {
  ...graded,
  status: 'confirmed',
  receipt: {
    attempt_id: open.id,
    project_id: project.id,
    memory: { ...memory, introduced: true },
    auto_rating: 3,
    rating: 4,
    correct: true,
    at: open.issued_at,
    is_introduction: true,
  },
}
export const queued: components['schemas']['StudyPlanRead'] = {
  ...plan,
  queue_total: 1,
  queue: [
    { kind: 'new', memory, memory_version: 'version:first' },
  ],
}
export const empty: components['schemas']['StudyPlanRead'] = {
  ...queued,
  queue_total: 0,
  queue: [],
  today: { new: 5, reviews: 5 },
}
