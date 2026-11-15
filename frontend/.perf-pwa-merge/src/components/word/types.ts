import type { graphEdges, graphNodes } from '@/design/tokens'

// Presentation models; page adapters own mapping from generated API types.
export type NodeType = keyof typeof graphNodes
export type RelationType = keyof typeof graphEdges
export type PartOfSpeech = 'noun' | 'verb' | 'adjective' | 'adverb' | 'pronoun' | 'preposition' | 'conjunction' | 'interjection' | 'determiner' | 'numeral' | 'particle' | 'other'
export type ExamTag = 'ielts' | 'toefl' | 'cet4' | 'cet6' | 'gre'
export interface Pronunciation {
  id: string
  ipa: string
  accent: 'US' | 'UK'
  audioUrl?: string
}
export interface SenseView {
  id: string
  definition: string
  gloss?: string
  common?: boolean
  hidden?: boolean
  overridden?: boolean
  register?: string
  domain?: string
  examples?: { text: string, translation?: string }[]
}
export interface LexemeView {
  id: string
  pos: PartOfSpeech
  pronunciations?: Pronunciation[]
  senses: SenseView[]
}
export interface LemmaView {
  id: string
  text: string
  kind: 'word' | 'phrase'
  frequencyBand?: string
  examTags?: ExamTag[]
}
export interface LemmaBranch {
  lemma: LemmaView
  lexemes: LexemeView[]
}
