import type { components } from '@/api/schema'
import type { LemmaBranch, PartOfSpeech } from '@/components/word/types'

export type Candidate = components['schemas']['Candidate']
const partsOfSpeech = new Set<PartOfSpeech>([
  'noun',
  'verb',
  'adjective',
  'adverb',
  'pronoun',
  'preposition',
  'conjunction',
  'interjection',
  'determiner',
  'numeral',
  'particle',
  'other',
])

export function candidateView(candidate: Candidate): LemmaBranch {
  return {
    lemma: {
      id: JSON.stringify(candidate.lemma.id),
      text: candidate.lemma.text,
      kind: candidate.lemma.kind,
    },
    lexemes: candidate.lexemes.map(({ lexeme, senses, glosses }) => ({
      id: JSON.stringify(lexeme.id),
      pos: partsOfSpeech.has(lexeme.pos as PartOfSpeech)
        ? lexeme.pos as PartOfSpeech
        : 'other',
      senses: senses.map(sense => ({
        id: JSON.stringify(sense.id),
        definition: sense.definition,
        gloss: sense.gloss_zh ?? glosses.find(gloss =>
          JSON.stringify(gloss.sense_id) === JSON.stringify(sense.id))?.gloss,
        common: sense.common,
        register: sense.register.join(', '),
        domain: sense.domain.join(', '),
        examples: sense.examples.flatMap(example => typeof example.text === 'string'
          ? [
              {
                text: example.text,
                translation: typeof example.translation === 'string'
                  ? example.translation
                  : undefined,
              },
            ]
          : []),
      })),
    })),
  }
}
