const lightColors = {
  'primary': '#1976D2',
  'primary-hover': '#1E88E5',
  'primary-pressed': '#1565C0',
  'primary-soft': '#E3F2FD',
  'on-primary': '#FFFFFF',
  'info': '#0288D1',
  'info-soft': '#E1F5FE',
  'success': '#2E7D32',
  'success-soft': '#E8F5E9',
  'warning': '#ED6C02',
  'warning-soft': '#FFF3E0',
  'error': '#D32F2F',
  'error-soft': '#FFEBEE',
  'text': '#212121',
  'text-muted': '#616161',
  'text-disabled': '#9E9E9E',
  'border': '#E0E0E0',
  'divider': '#EEEEEE',
  'bg': '#EEEEEE',
  'surface': '#FFFFFF',
  'surface-raised': '#FFFFFF',
} as const

const darkColors = {
  'primary': '#64B5F6',
  'primary-hover': '#90CAF9',
  'primary-pressed': '#42A5F5',
  'primary-soft': '#0D2A4A',
  'on-primary': '#0D1B2A',
  'info': '#29B6F6',
  'info-soft': '#062E3F',
  'success': '#66BB6A',
  'success-soft': '#0F2E12',
  'warning': '#FFA726',
  'warning-soft': '#3A2406',
  'error': '#EF5350',
  'error-soft': '#3B1012',
  'text': '#E3E3E3',
  'text-muted': '#A8A8A8',
  'text-disabled': '#6B6B6B',
  'border': '#3A3A3A',
  'divider': '#2A2A2A',
  'bg': '#121212',
  'surface': '#1A1A1A',
  'surface-raised': '#232323',
} as const satisfies Record<keyof typeof lightColors, string>

const lightNodes = {
  lemma: '#37474F',
  lexeme: '#5E35B1',
  sense: '#3949AB',
  phrase: '#C2185B',
  morpheme: '#EF6C00',
  sentence: '#00796B',
  passage: '#558B2F',
  tag: '#757575',
} as const

const darkNodes = {
  lemma: '#B0BEC5',
  lexeme: '#B39DDB',
  sense: '#9FA8DA',
  phrase: '#F48FB1',
  morpheme: '#FFB74D',
  sentence: '#4DB6AC',
  passage: '#AED581',
  tag: '#BDBDBD',
} as const satisfies Record<keyof typeof lightNodes, string>

type ColorName = keyof typeof lightColors
type NodeName = keyof typeof lightNodes
type GraphColor = ColorName | `node-${NodeName}`

export const graphNodes = {
  lemma: { shape: 'round-rectangle', size: 'large' },
  lexeme: { shape: 'round-rectangle' },
  sense: { shape: 'ellipse' },
  phrase: { shape: 'round-hexagon' },
  morpheme: { shape: 'diamond' },
  sentence: { shape: 'rectangle' },
  passage: { shape: 'barrel' },
  tag: { shape: 'tag' },
} as const satisfies Record<NodeName, { shape: string, size?: string }>

export const graphMetrics = {
  maxFitZoom: 1,
  nodeSize: 44,
  focusSize: 56,
  borderWidth: 3,
  edgeWidth: 1,
  labelSize: 12,
  labelWidth: 120,
  canvasHeight: '28rem',
  controlWidth: '10rem',
} as const

export const graphEdges = {
  synonym: { color: 'success', line: 'solid' },
  antonym: { color: 'error', line: 'solid' },
  hypernym: { color: 'node-sense', line: 'solid', arrow: true },
  hyponym: { color: 'node-sense', line: 'solid', arrow: true },
  confusable: { color: 'warning', line: 'dashed' },
  derives_to: { color: 'node-lexeme', line: 'dashed', arrow: true },
  composed_of: { color: 'node-morpheme', line: 'dotted' },
  contains: { color: 'node-phrase', line: 'solid' },
  used_in: { color: 'node-sentence', line: 'thin' },
  member_of: { color: 'node-tag', line: 'thin' },
  default: { color: 'text-muted', line: 'thin' },
} as const satisfies Record<string, { color: GraphColor, line: string, arrow?: boolean }>

export const ratingAliases = {
  again: 'error',
  hard: 'warning',
  good: 'success',
  easy: 'info',
} as const satisfies Record<string, ColorName>

export const typography = {
  font: {
    sans: '"Roboto", "PingFang SC", "Microsoft YaHei", "Noto Sans CJK SC", system-ui, sans-serif',
    serif: '"Roboto Serif", Georgia, serif',
    ipa: '"Noto Sans", "Roboto", sans-serif',
    mono: '"Roboto Mono", ui-monospace, monospace',
  },
  size: {
    'xs': '0.75rem',
    'sm': '0.875rem',
    'base': '1rem',
    'lg': '1.25rem',
    'xl': '1.5rem',
    '2xl': '2rem',
    '3xl': '2.5rem',
  },
  weight: {
    regular: '400',
    medium: '500',
    semibold: '600',
    bold: '700',
  },
  lineHeight: { tight: '1.25', normal: '1.5', relaxed: '1.75' },
} as const

export const spacing = {
  0: '0',
  0.5: '2px',
  1: '4px',
  2: '8px',
  3: '12px',
  4: '16px',
  6: '24px',
  8: '32px',
  12: '48px',
  16: '64px',
} as const

export const radius = {
  sm: '4px',
  md: '8px',
  lg: '12px',
  full: '9999px',
} as const

export const shadows = {
  light: {
    1: '0 1px 2px rgb(0 0 0 / .08), 0 1px 3px rgb(0 0 0 / .06)',
    2: '0 4px 12px rgb(0 0 0 / .12), 0 2px 4px rgb(0 0 0 / .08)',
  },
  dark: {
    1: '0 1px 2px rgb(0 0 0 / .24), 0 1px 3px rgb(0 0 0 / .18)',
    2: '0 4px 12px rgb(0 0 0 / .36), 0 2px 4px rgb(0 0 0 / .24)',
  },
} as const

export const motion = {
  duration: { fast: '150ms', normal: '250ms', slow: '400ms' },
  reducedDuration: '0ms',
  easing: {
    standard: 'cubic-bezier(0.2, 0, 0, 1)',
    decelerate: 'cubic-bezier(0.05, 0.7, 0.1, 1)',
  },
} as const

const bottomNavHeight = '56px'
const breakpoints = {
  sm: '640px',
  md: '768px',
  lg: '1024px',
  xl: '1280px',
} as const

export const layout = {
  breakpoints,
  pagePadding: { mobile: spacing[4], lg: spacing[6] },
  sectionGap: spacing[6],
  cardGap: spacing[3],
  navigationBreakpoint: breakpoints.lg,
  headerHeight: '56px',
  sidebarWidth: '240px',
  sidebarCollapsedWidth: '64px',
  bottomNavHeight,
  bottomNavWithSafeArea: `calc(${bottomNavHeight} + env(safe-area-inset-bottom))`,
  contentMaxWidth: '1200px',
  readingMaxWidth: '720px',
  controlHeight: { small: '28px', medium: '36px', large: '44px' },
  iconSize: { dense: '16px', default: '20px', nav: '24px' },
  touchTarget: '44px',
  focusRing: { width: '2px', style: 'solid', offset: '2px' },
} as const

function createTheme(
  baseColors: Record<ColorName, string>,
  nodes: Record<NodeName, string>,
  shadow: Record<keyof typeof shadows.light, string>,
) {
  function resolveColor(name: GraphColor) {
    return name.startsWith('node-')
      ? nodes[name.slice(5) as NodeName]
      : baseColors[name as ColorName]
  }

  const edges = Object.fromEntries(
    Object.entries(graphEdges).map(([name, edge]) => [
      name,
      resolveColor(edge.color),
    ]),
  ) as Record<keyof typeof graphEdges, string>
  const ratings = Object.fromEntries(
    Object.entries(ratingAliases).map(([name, color]) => [name, baseColors[color]]),
  ) as Record<keyof typeof ratingAliases, string>

  return {
    colors: { ...baseColors, focus: baseColors.primary },
    nodes,
    edges,
    ratings,
    shadows: shadow,
  }
}

export const themes = {
  light: createTheme(lightColors, lightNodes, shadows.light),
  dark: createTheme(darkColors, darkNodes, shadows.dark),
} as const

export type ThemeMode = keyof typeof themes
