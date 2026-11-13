import type { Container } from 'postcss'
import postcss from 'postcss'
import { createGenerator } from 'unocss'
import { describe, expect, it } from 'vitest'
import { fontLicenseAssets, generateFontCss } from '../../design-css-plugin'
import unoConfig from '../../uno.config'
import { generateTokenCss } from './css-vars'
import { createCytoscapeStyle } from './cytoscape-style'
import { darkThemeOverrides, themeOverrides } from './naive-theme'
import { layout, motion, radius, spacing, themes, typography } from './tokens'

function declarations(container: Container) {
  const result: Record<string, string> = {}
  container.walkDecls((declaration) => {
    result[declaration.prop] = declaration.value
  })
  return result
}

function variables(prefix: string, values: Record<string, string>) {
  return Object.fromEntries(Object.entries(values).map(([name, value]) => [
    `--pw-${prefix}-${name.replaceAll('.', '-')}`,
    value,
  ]))
}

function themeVariables(theme: typeof themes.light) {
  return {
    ...variables('color', theme.colors),
    ...variables('node', theme.nodes),
    ...variables('edge', theme.edges),
    ...variables('rating', theme.ratings),
    ...variables('shadow', theme.shadows),
  }
}

describe('token generators', () => {
  it('emits every light, dark, and shared token as CSS variables', () => {
    const root = postcss.parse(generateTokenCss())
    const lightRule = root.nodes.find(node => node.type === 'rule' && node.selector === ':root')
    const darkRule = root.nodes.find(node => node.type === 'rule' && node.selector === '[data-theme=\'dark\']')
    expect(lightRule?.type).toBe('rule')
    expect(darkRule?.type).toBe('rule')
    if (lightRule?.type !== 'rule' || darkRule?.type !== 'rule')
      return

    const shared = {
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
      '--pw-focus-ring': 'var(--pw-focus-ring-width) var(--pw-focus-ring-style) var(--pw-color-focus)',
    }
    const onlyVariables = (rule: Container) => Object.fromEntries(
      Object.entries(declarations(rule)).filter(([key]) => key.startsWith('--pw-')),
    )
    expect(onlyVariables(lightRule)).toEqual({
      ...themeVariables(themes.light),
      ...shared,
    })
    expect(onlyVariables(darkRule)).toEqual(themeVariables(themes.dark))
  })

  it('sets every duration to zero for reduced motion in both color schemes', () => {
    const root = postcss.parse(generateTokenCss())
    const media = root.nodes.find(node => node.type === 'atrule' && node.params === '(prefers-reduced-motion: reduce)')
    expect(media?.type).toBe('atrule')
    if (media?.type !== 'atrule')
      return
    const rule = media.nodes?.find(node => node.type === 'rule')
    expect(rule?.type === 'rule' && rule.selector).toBe(':root, [data-theme=\'dark\']')
    if (rule?.type !== 'rule')
      return
    expect(declarations(rule)).toEqual(Object.fromEntries(
      Object.keys(motion.duration).map(name => [`--pw-duration-${name}`, motion.reducedDuration]),
    ))
    const globalRule = media.nodes?.find(node => node.type === 'rule' && node.selector === '*, *::before, *::after')
    expect(globalRule?.type).toBe('rule')
    if (globalRule?.type === 'rule') {
      expect(declarations(globalRule)).toEqual({
        'animation-duration': motion.reducedDuration,
        'animation-delay': motion.reducedDuration,
        'transition-duration': motion.reducedDuration,
        'transition-delay': motion.reducedDuration,
      })
      globalRule.walkDecls(declaration => expect(declaration.important).toBe(true))
    }
  })

  it('generates Naive UI overrides from each theme, including dimensions', () => {
    for (const [mode, overrides] of [
      ['light', themeOverrides],
      ['dark', darkThemeOverrides],
    ] as const) {
      const { colors, shadows } = themes[mode]
      expect(overrides.common).toMatchObject({
        primaryColor: colors.primary,
        primaryColorHover: colors['primary-hover'],
        primaryColorPressed: colors['primary-pressed'],
        infoColor: colors.info,
        successColor: colors.success,
        warningColor: colors.warning,
        errorColor: colors.error,
        borderColor: colors.border,
        bodyColor: colors.bg,
        cardColor: colors['surface-raised'],
        fontFamily: typography.font.sans,
        fontFamilyMono: typography.font.mono,
        borderRadiusSmall: radius.sm,
        borderRadius: radius.md,
        heightSmall: layout.controlHeight.small,
        heightMedium: layout.controlHeight.medium,
        heightLarge: layout.controlHeight.large,
        boxShadow1: shadows[1],
        boxShadow2: shadows[2],
      })
      expect(overrides.common?.primaryColor).toMatch(/^#[\dA-F]{6}$/)
    }
  })

  it('replaces Uno defaults and generates token-backed utilities', async () => {
    const uno = await createGenerator(unoConfig)
    expect(uno.config.theme.colors).not.toHaveProperty('red')
    expect(Object.keys(uno.config.theme.fontSize ?? {}).sort()).toEqual(Object.keys(typography.size).sort())
    expect(Object.keys(uno.config.theme.borderRadius ?? {}).sort()).toEqual(Object.keys(radius).sort())
    expect(Object.keys(uno.config.theme.boxShadow ?? {}).sort()).toEqual(Object.keys(themes.light.shadows).sort())
    expect(Object.keys(uno.config.theme.spacing ?? {}).sort()).toEqual(Object.keys(spacing).sort())

    const result = await uno.generate(
      'p-0.5 lg:p-6 bg-primary text-fg text-sm border-base rounded-md shadow-1 font-serif focus-visible:pw-focus-ring bg-node-sense text-node-tag bg-rating-again',
      { preflights: false },
    )
    for (const variable of [
      '--pw-space-0-5',
      '--pw-space-6',
      '--pw-color-primary',
      '--pw-color-text',
      '--pw-font-size-sm',
      '--pw-line-height-normal',
      '--pw-color-border',
      '--pw-radius-md',
      '--pw-shadow-1',
      '--pw-font-serif',
      '--pw-focus-ring',
      '--pw-focus-ring-offset',
      '--pw-node-sense',
      '--pw-node-tag',
      '--pw-rating-again',
    ])
      expect(result.css).toContain(`var(${variable})`)
    expect(result.css).toContain(`min-width: ${layout.breakpoints.lg}`)
    expect(result.css).toContain(':focus-visible')
  })

  it('blocklists unsupported classes rather than emitting their CSS', async () => {
    const uno = await createGenerator(unoConfig)
    for (const name of [
      'p-[13px]',
      'bg-red-500',
      'hover:bg-red-500',
      'p-5',
      'p5',
      'pa-5',
      'gap-col-5',
      'translate-5',
      'w5',
      'p-13px',
      'p13px',
      'p-1rem',
      'm--2',
      'bg-hex-fff',
      'text-#fff',
      'text-4xl',
      'leading-8',
      'font-800',
      'rounded-xl',
      'shadow-lg',
      'focus-ring',
      'focus-visible:ring-3',
      'duration-150ms',
    ]) {
      expect(uno.getBlocked(name), name).toBeTruthy()
      expect((await uno.generate(name, { preflights: false })).matched.has(name), name).toBe(false)
    }
  })

  it('self-hosts only Latin and Latin-ext variable fonts under the documented family names', () => {
    const faces: Record<string, string>[] = []
    postcss.parse(generateFontCss()).walkAtRules('font-face', (face) => {
      faces.push(declarations(face))
    })
    const families = Object.values(typography.font).map(value => /^"([^"]+)"/.exec(value)![1])
    expect(faces).toHaveLength(families.length * 2)
    for (const family of families) {
      const familyFaces = faces.filter(face => face['font-family'] === `"${family}"`)
      expect(familyFaces).toHaveLength(2)
      expect(familyFaces.map(face => face.src)).toEqual(expect.arrayContaining([
        expect.stringMatching(/@fontsource-variable\/[^/]+\/files\/[^/]+-latin-wght-normal\.woff2/),
        expect.stringMatching(/@fontsource-variable\/[^/]+\/files\/[^/]+-latin-ext-wght-normal\.woff2/),
      ]))
      for (const face of familyFaces) {
        expect(face['font-display']).toBe('swap')
        expect(face['unicode-range']).toBeTruthy()
      }
    }
    const licenses = fontLicenseAssets()
    expect(licenses).toHaveLength(families.length)
    expect(new Set(licenses.map(license => license.fileName)).size).toBe(families.length)
    for (const license of licenses)
      expect(license.source).toContain('SIL OPEN FONT LICENSE')
  })

  it('rebuilds the Cytoscape stub from the current computed theme', () => {
    const element = document.createElement('div')
    document.body.append(element)
    element.style.setProperty('--pw-color-text', themes.light.colors.text)
    element.style.setProperty('--pw-node-sense', themes.light.nodes.sense)
    element.style.setProperty('--pw-edge-hypernym', themes.light.edges.hypernym)
    const light = createCytoscapeStyle(element)
    element.style.setProperty('--pw-node-sense', themes.dark.nodes.sense)
    element.style.setProperty('--pw-edge-hypernym', themes.dark.edges.hypernym)
    const dark = createCytoscapeStyle(element)
    expect(light.find(rule => rule.selector === 'node[type = "sense"]')?.style['background-color']).toBe(themes.light.nodes.sense)
    expect(dark.find(rule => rule.selector === 'node[type = "sense"]')?.style['background-color']).toBe(themes.dark.nodes.sense)
    expect(dark.find(rule => rule.selector === 'edge[type = "hypernym"]')?.style).toMatchObject({
      'line-color': themes.dark.edges.hypernym,
      'target-arrow-shape': 'triangle',
    })
    element.remove()
  })
})
