import type { LemmaBranch } from '@/components/word/types'

export const wordSamples: LemmaBranch[] = [
  {
    lemma: {
      id: 'bank',
      text: 'bank',
      kind: 'word',
      examTags: ['ielts', 'cet4'],
    },
    lexemes: [
      {
        id: 'bank-noun',
        pos: 'noun',
        pronunciations: [
          { id: 'bank-us', ipa: 'bæŋk', accent: 'US' },
          { id: 'bank-uk', ipa: 'bæŋk', accent: 'UK' },
        ],
        senses: [
          {
            id: 'bank-money',
            definition: 'An organization that keeps and lends money.',
            gloss: '银行；金融机构',
            common: true,
            examples: [
              { text: 'She went to the bank.', translation: '她去了银行。' },
            ],
          },
          {
            id: 'bank-river',
            definition: 'The land alongside a river.',
            gloss: '河岸',
            overridden: true,
            domain: 'geography',
            examples: [
              { text: 'We sat on the river bank.', translation: '我们坐在河岸上。' },
            ],
          },
          {
            id: 'bank-row',
            definition: 'A row or tier of objects.',
            gloss: '一排；一组',
            hidden: true,
          },
        ],
      },
      {
        id: 'bank-verb',
        pos: 'verb',
        senses: [
          {
            id: 'bank-save',
            definition: 'To deposit money in a bank.',
            gloss: '存款',
            common: true,
          },
        ],
      },
    ],
  },
  {
    lemma: {
      id: 'look-up',
      text: 'look up',
      kind: 'phrase',
      examTags: ['toefl'],
    },
    lexemes: [
      {
        id: 'look-up-verb',
        pos: 'verb',
        pronunciations: [
          { id: 'look-up-us', ipa: 'lʊk ʌp', accent: 'US' },
        ],
        senses: [
          {
            id: 'look-up-search',
            definition: 'To search for information.',
            gloss: '查阅',
            common: true,
          },
        ],
      },
    ],
  },
]

// A local generated tone exercises media controls without a network or authentication dependency.
export function previewAudioSource() {
  const samples = 4000
  const buffer = new ArrayBuffer(44 + samples)
  const view = new DataView(buffer)
  function text(offset: number, value: string) {
    [...value].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)))
  }
  text(0, 'RIFF')
  view.setUint32(4, 36 + samples, true)
  text(8, 'WAVE')
  text(12, 'fmt ')
  view.setUint32(16, 16, true)
  view.setUint16(20, 1, true)
  view.setUint16(22, 1, true)
  view.setUint32(24, 8000, true)
  view.setUint32(28, 8000, true)
  view.setUint16(32, 1, true)
  view.setUint16(34, 8, true)
  text(36, 'data')
  view.setUint32(40, samples, true)
  for (let index = 0; index < samples; index++)
    view.setUint8(44 + index, 128 + Math.round(20 * Math.sin(index * 2 * Math.PI * 440 / 8000)))
  return URL.createObjectURL(new Blob([buffer], { type: 'audio/wav' }))
}
