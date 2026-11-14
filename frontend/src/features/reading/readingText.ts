import type { components } from '@/api/schema'

export type Reading = components['schemas']['PassageRead']
export type Occurrence = components['schemas']['Occurrence']
export type Part = components['schemas']['SentencePart']

export function readingSegments(reading: Reading) {
  const points = Array.from(reading.passage.text)
  const segments: { text: string, occurrence?: Occurrence, sentenceId?: string }[] = []
  let cursor = 0
  for (const part of [...reading.sentences].sort((a, b) => a.order - b.order)) {
    for (const occurrence of [
      ...(part.occurrences ?? []),
    ].sort((a, b) => a.span[0] - b.span[0])) {
      const start = part.span[0] + occurrence.span[0]
      const end = part.span[0] + occurrence.span[1]
      if (start < cursor || end > part.span[1] || end <= start)
        continue
      if (start > cursor) {
        segments.push({
          text: points.slice(cursor, start).join(''),
        })
      }
      segments.push({
        text: points.slice(start, end).join(''),
        occurrence,
        sentenceId: part.sentence.id,
      })
      cursor = end
    }
  }
  if (cursor < points.length) {
    segments.push({
      text: points.slice(cursor).join(''),
    })
  }
  return segments
}

export function occurrenceState(reading: Reading, occurrence: Occurrence) {
  if (!occurrence.sense_id)
    return 'unlinked'
  return reading.project_senses?.some(sense => sense.id === occurrence.sense_id)
    ? 'selected'
    : 'outside'
}
