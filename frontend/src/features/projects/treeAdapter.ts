import type { components } from '@/api/schema'
import type { LemmaBranch, PartOfSpeech } from '@/components/word/types'

export type TreeLemma = components['schemas']['ProjectTreeLemmaRead']
export type TreeTable = 'lemma' | 'lexeme' | 'sense'

const parts = new Set([
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
function text(value: unknown) {
  return typeof value === 'string'
    ? value
    : ''
}
function strings(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === 'string').join(', ')
    : ''
}

export function treeView(items: TreeLemma[], showHidden: boolean, sourceLang: string): LemmaBranch[] {
  return items.filter(item => showHidden || !item.effective_hidden).map(item => ({
    lemma: {
      id: item.lemma.id,
      text: text(item.lemma.fields.text),
      kind: item.lemma.fields.kind === 'phrase'
        ? 'phrase'
        : 'word',
      frequencyBand: text(item.lemma.fields.cefr) || undefined,
    },
    lexemes: item.lexemes.flatMap((group) => {
      const senses = group.senses.filter(sense => showHidden || !sense.effective_hidden)
      if (!showHidden && (group.effective_hidden || !senses.length))
        return []
      const pos = text(group.lexeme.fields.pos)
      return [
        {
          id: group.lexeme.id,
          pos: (parts.has(pos)
            ? pos
            : 'other') as PartOfSpeech,
          senses: senses.map(({ sense, effective_hidden }) => {
            const fields = sense.fields
            const gloss = fields.gloss && typeof fields.gloss === 'object'
              ? (fields.gloss as Record<string, unknown>)[sourceLang]
              : undefined
            return {
              id: sense.id,
              definition: text(fields.definition),
              gloss: text(gloss) || undefined,
              common: fields.common === true,
              hidden: showHidden && effective_hidden,
              register: strings(fields.register),
              domain: strings(fields.domain),
              examples: Array.isArray(fields.examples)
                ? fields.examples.flatMap(example =>
                    typeof example === 'string'
                      ? [
                          { text: example },
                        ]
                      : [])
                : [],
            }
          }),
        },
      ]
    }),
  }))
}

export function findTreeNode(items: TreeLemma[], table: TreeTable, id: string) {
  for (const lemma of items) {
    if (table === 'lemma' && lemma.lemma.id === id)
      return lemma
    for (const lexeme of lemma.lexemes) {
      if (table === 'lexeme' && lexeme.lexeme.id === id)
        return lexeme
      const sense = lexeme.senses.find(item => table === 'sense' && item.sense.id === id)
      if (sense)
        return sense
    }
  }
}

export function updateTreeVisibility(items: TreeLemma[], table: TreeTable, id: string, hidden: boolean) {
  const node = findTreeNode(items, table, id)
  if (node)
    node.hidden = hidden
  for (const lemma of items) {
    lemma.effective_hidden = lemma.hidden
    for (const lexeme of lemma.lexemes) {
      lexeme.effective_hidden = lemma.effective_hidden || lexeme.hidden
      for (const sense of lexeme.senses)
        sense.effective_hidden = lexeme.effective_hidden || sense.hidden
    }
  }
}
