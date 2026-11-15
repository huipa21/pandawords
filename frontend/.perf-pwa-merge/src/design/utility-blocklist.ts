import { spacing } from './tokens.ts'

const palette = /(?:^|-)(?:slate|gray|grey|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose|warmgray|coolgray|truegray|bluegray|black|white|transparent|current|inherit)(?:-\d{1,3})?(?:\/[\d.]+)?$/i
const rawColor = /#|(?:^|-)hex-[\da-f]+(?:\/[\d.]+)?$/i
const rawLength = /[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:px|rem|em|vh|vw|vmin|vmax|dvh|dvw|svh|svw|lvh|lvw|ch|ex|lh|cm|mm|in|pt|pc|q|%)$/i
const numericSpacing = /^!?-?(?:[mp](?:[atrblxyse]|[bi][se]|-(?:[trblxyse]|block|inline))?-?|(?:flex-|grid-)?gap(?:-(?:x|y|col|row))?-?|space-[xy]-|inset(?:-[xy])?-|top-|right-|bottom-|left-|start-|end-|(?:min-|max-)?[wh]-?|size-|(?:transform-)?translate(?:-[xyz])?-|scroll-[mp][trblxyse]?-)(-?\d+(?:\.\d+)?)$/
const unsupportedTextSize = /^!?text-(?:size-)?(?:(?:[4-9]|\d{2,})xl|\d+(?:\.\d+)?)$/
const unsupportedRadius = /^!?rounded(?:-[trblse]{1,2})?(?:-(?!sm$|md$|lg$|full$)[\w-]+)?$/
const unsupportedShadow = /^!?shadow(?:-(?!1$|2$)[\w-]+)?$/
const rawTypography = /^!?(?:(?:font-)?(?:leading|lh|line-height)-\d|(?:font|font-weight|fw)-\d)/
const rawDuration = /^!?(?:duration|transition-duration)-\d/
const rawFocusWidth = /^!?(?:ring(?:-offset)?|outline)-\d/

export function blockedUtilityReason(candidate: string): string | undefined {
  if (candidate.includes('[') || candidate.includes(']'))
    return 'Arbitrary utilities are not design tokens.'

  const utility = candidate.split(':').at(-1) ?? candidate
  if (palette.test(utility) || rawColor.test(utility))
    return 'Raw and default palette colors are not design tokens.'
  if (rawLength.test(utility))
    return 'Literal lengths are not design tokens.'

  const step = numericSpacing.exec(utility)?.[1]
  if (step?.startsWith('-'))
    return 'Use the negative token form, such as -m-2.'
  if (step && !(step in spacing))
    return 'This spacing step is not in the token scale.'

  if (unsupportedTextSize.test(utility))
    return 'This font size is not in the token scale.'
  if (rawTypography.test(utility))
    return 'Use a named typography token.'
  if (unsupportedRadius.test(utility))
    return 'This radius is not in the token scale.'
  if (unsupportedShadow.test(utility))
    return 'This shadow is not in the token scale.'
  if (rawDuration.test(utility))
    return 'Use a named motion-duration token.'
  if (rawFocusWidth.test(utility))
    return 'Use pw-focus-ring for the tokenized focus outline.'
  if (utility === 'focus-ring')
    return 'Use pw-focus-ring for the tokenized focus outline.'
  return undefined
}
