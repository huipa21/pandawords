import type { components } from '@/api/schema'
import type { LemmaView, PartOfSpeech, SenseView } from '@/components/word/types'

export type DictionaryRecord = components['schemas']['DictionaryRecordRead']
export type DictionaryEntry = components['schemas']['DictionaryEntryRead']
export type Override = components['schemas']['OverrideRead']
export type OverrideFields = components['schemas']['OverrideFields-Input']

export function object(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value))
    : {}
}

export function text(value: unknown) {
  return typeof value === 'string'
    ? value
    : ''
}

export function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string')
    : []
}

export function lemmaView(record: DictionaryRecord): LemmaView {
  return {
    id: record.id,
    text: text(record.fields.text),
    kind: record.fields.kind === 'phrase'
      ? 'phrase'
      : 'word',
    frequencyBand: typeof record.fields.freq_zipf === 'number' && Number.isFinite(record.fields.freq_zipf)
      ? String(record.fields.freq_zipf)
      : undefined,
    examTags: strings(record.fields.exam_tags).filter(
      (tag): tag is NonNullable<LemmaView['examTags']>[number] => [
        'ielts',
        'toefl',
        'cet4',
        'cet6',
        'gre',
      ].includes(tag),
    ),
  }
}

export function posView(value: unknown): PartOfSpeech {
  switch (value) {
    case 'noun': case 'verb': case 'adjective': case 'adverb': case 'pronoun':
    case 'preposition': case 'conjunction': case 'interjection': case 'determiner':
    case 'numeral': case 'particle': return value
    default: return 'other'
  }
}

export function pronunciations(record: DictionaryRecord) {
  const values = record.fields.pron
  if (!Array.isArray(values))
    return []
  return values.flatMap((value, index) => {
    const pron = object(value)
    if (pron.accent !== 'US' && pron.accent !== 'UK')
      return []
    const accent: 'US' | 'UK' = pron.accent
    return [
      {
        id: `${record.id}:${index}`,
        ipa: text(pron.ipa),
        accent,
        mediaId: text(pron.audio),
      },
    ]
  })
}

export function senseView(record: DictionaryRecord, overridden: boolean): SenseView {
  return {
    id: record.id,
    definition: text(record.fields.definition),
    gloss: text(object(record.fields.gloss).zh),
    common: record.fields.common === true,
    overridden,
    register: strings(record.fields.register).join(', '),
    domain: strings(record.fields.domain).join(', '),
    examples: strings(record.fields.examples).map(text => ({ text })),
  }
}

export function entryRecords(entry: DictionaryEntry) {
  return [
    entry.lemma,
    ...entry.lexemes.flatMap(item => [item.lexeme, ...item.senses]),
  ]
}
