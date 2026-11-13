import { layout, motion, radius, spacing, themes, typography } from './tokens.ts'

function variables(prefix: string, values: Record<string, string>) {
  return Object.entries(values).map(([name, value]) =>
    `  --pw-${prefix}-${name.replaceAll('.', '-')}: ${value};`,
  )
}

function themeVariables(theme: typeof themes.light) {
  return [
    ...variables('color', theme.colors),
    ...variables('node', theme.nodes),
    ...variables('edge', theme.edges),
    ...variables('rating', theme.ratings),
    ...variables('shadow', theme.shadows),
  ]
}

export function generateTokenCss() {
  const common = [
    ...variables('font', typography.font),
    ...variables('font-size', typography.size),
    ...variables('font-weight', typography.weight),
    ...variables('line-height', typography.lineHeight),
    ...variables('space', spacing),
    ...variables('radius', radius),
    ...variables('duration', motion.duration),
    ...variables('ease', motion.easing),
    ...variables('breakpoint', layout.breakpoints),
    ...variables('layout', {
      'page-padding-mobile': layout.pagePadding.mobile,
      'page-padding-lg': layout.pagePadding.lg,
      'section-gap': layout.sectionGap,
      'card-gap': layout.cardGap,
      'navigation-breakpoint': layout.navigationBreakpoint,
      'header-height': layout.headerHeight,
      'sidebar-width': layout.sidebarWidth,
      'sidebar-collapsed-width': layout.sidebarCollapsedWidth,
      'bottom-nav-height': layout.bottomNavHeight,
      'bottom-nav-with-safe-area': layout.bottomNavWithSafeArea,
      'content-max-width': layout.contentMaxWidth,
      'reading-max-width': layout.readingMaxWidth,
      'touch-target': layout.touchTarget,
    }),
    ...variables('control-height', layout.controlHeight),
    ...variables('icon-size', layout.iconSize),
    ...variables('focus-ring', layout.focusRing),
    '  --pw-focus-ring: var(--pw-focus-ring-width) var(--pw-focus-ring-style) var(--pw-color-focus);',
  ]
  const reducedMotion = Object.keys(motion.duration)
    .map(name => `    --pw-duration-${name}: ${motion.reducedDuration};`)

  return [
    ':root {',
    ...themeVariables(themes.light),
    ...common,
    '  color-scheme: light;',
    '  font-family: var(--pw-font-sans);',
    '  font-size: var(--pw-font-size-base);',
    '  line-height: var(--pw-line-height-normal);',
    '  color: var(--pw-color-text);',
    '  background-color: var(--pw-color-bg);',
    '}',
    '[data-theme=\'dark\'] {',
    ...themeVariables(themes.dark),
    '  color-scheme: dark;',
    '}',
    '@media (prefers-reduced-motion: reduce) {',
    '  :root, [data-theme=\'dark\'] {',
    ...reducedMotion,
    '  }',
    '  *, *::before, *::after {',
    `    animation-duration: ${motion.reducedDuration} !important;`,
    `    animation-delay: ${motion.reducedDuration} !important;`,
    `    transition-duration: ${motion.reducedDuration} !important;`,
    `    transition-delay: ${motion.reducedDuration} !important;`,
    '  }',
    '}',
  ].join('\n')
}
