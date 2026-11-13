import type { PresetWind3Theme } from 'unocss'
import { layout, motion, radius, spacing, themes, typography } from './tokens.ts'

function cssVariables(prefix: string, values: Record<string, string>) {
  return Object.fromEntries(
    Object.keys(values).map(name => [name, `var(--pw-${prefix}-${name.replaceAll('.', '-')})`]),
  )
}

const colors = cssVariables('color', themes.light.colors)
const { text, 'text-muted': muted, 'text-disabled': disabled, border, bg, 'surface-raised': raised, ...semantic } = colors

export const unoTheme: PresetWind3Theme = {
  colors: {
    ...semantic,
    fg: text,
    muted,
    disabled,
    base: border,
    page: bg,
    raised,
    node: cssVariables('node', themes.light.nodes),
    edge: cssVariables('edge', themes.light.edges),
    rating: cssVariables('rating', themes.light.ratings),
  },
  fontFamily: cssVariables('font', typography.font),
  fontSize: Object.fromEntries(
    Object.keys(typography.size).map(name => [
      name,
      [`var(--pw-font-size-${name})`, 'var(--pw-line-height-normal)'],
    ]),
  ),
  fontWeight: cssVariables('font-weight', typography.weight),
  lineHeight: cssVariables('line-height', typography.lineHeight),
  spacing: cssVariables('space', spacing),
  borderRadius: cssVariables('radius', radius),
  boxShadow: cssVariables('shadow', themes.light.shadows),
  duration: cssVariables('duration', motion.duration),
  easing: cssVariables('ease', motion.easing),
  breakpoints: layout.breakpoints,
  width: {
    'sidebar': 'var(--pw-layout-sidebar-width)',
    'sidebar-collapsed': 'var(--pw-layout-sidebar-collapsed-width)',
  },
  maxWidth: {
    content: 'var(--pw-layout-content-max-width)',
    reading: 'var(--pw-layout-reading-max-width)',
  },
  height: {
    'header': 'var(--pw-layout-header-height)',
    'bottom-nav': 'var(--pw-layout-bottom-nav-with-safe-area)',
    'control-small': 'var(--pw-control-height-small)',
    'control-medium': 'var(--pw-control-height-medium)',
    'control-large': 'var(--pw-control-height-large)',
  },
}
