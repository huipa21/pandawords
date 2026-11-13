import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import process from 'node:process'
import { describe, expect, it } from 'vitest'
import {
  graphEdges,
  graphNodes,
  layout,
  motion,
  radius,
  ratingAliases,
  shadows,
  spacing,
  themes,
  typography,
} from './tokens'

const documentation = readFileSync(resolve(process.cwd(), '..', 'docs', 'ui', 'tokens.md'), 'utf8')

function section(heading: string) {
  const start = documentation.indexOf(`## ${heading}`)
  if (start < 0)
    throw new Error(`Missing token documentation: ${heading}`)
  const next = documentation.indexOf('\n## ', start + 3)
  return documentation.slice(start, next < 0
    ? undefined
    : next)
}

function rows(heading: string) {
  return section(heading).split('\n').filter(line => line.startsWith('|') && !line.startsWith('|---')).slice(1).map(line => line.slice(1, -1).split('|').map(cell => cell.trim()))
}

function names(value: string) {
  return [
    ...value.matchAll(/`([^`]+)`/g),
  ].map(match => match[1]!)
}

function documentedNumbers(value: string) {
  return [
    ...value.matchAll(/\d+(?:\.\d+)?/g),
  ].map(match => Number(match[0]))
}

describe('documented design tokens', () => {
  it('defines identical keys for both themes', () => {
    for (const group of Object.keys(themes.light) as (keyof typeof themes.light)[])
      expect(Object.keys(themes.dark[group]).sort()).toEqual(Object.keys(themes.light[group]).sort())
  })

  it('matches every semantic color and node color and shape', () => {
    const documentedColors: string[] = []
    for (const [label, , light, dark] of rows('Color — semantic')) {
      const keys = names(label!)
      documentedColors.push(...keys)
      for (const [mode, cell] of [
        ['light', light],
        ['dark', dark],
      ] as const) {
        const hex = cell!.match(/#[\dA-F]{6}/g) ?? []
        keys.forEach((key, index) => {
          const value = themes[mode].colors[key as keyof typeof themes.light.colors]
          expect(value).toBe(hex[index] ?? themes[mode].colors.primary)
          if (!hex[index])
            expect(cell).toContain('primary')
        })
      }
    }
    expect(documentedColors.sort()).toEqual(Object.keys(themes.light.colors).sort())

    const documentedNodes: string[] = []
    for (const [label, light, dark, shape] of rows('Color — graph nodes')) {
      const key = names(label!)[0]! as keyof typeof graphNodes
      documentedNodes.push(key)
      expect(themes.light.nodes[key]).toBe(names(light!)[0])
      expect(themes.dark.nodes[key]).toBe(names(dark!)[0])
      const node = graphNodes[key]
      expect(node.shape).toBe(shape!.split(' (')[0])
      expect('size' in node
        ? node.size
        : undefined).toBe(shape!.includes('(large)')
        ? 'large'
        : undefined)
    }
    expect(documentedNodes.sort()).toEqual(Object.keys(graphNodes).sort())
  })

  it('matches graph edge definitions and review-rating color aliases', () => {
    const documentedEdges: string[] = []
    for (const [label, color, line] of rows('Color — graph edges')) {
      for (const key of names(label!) as (keyof typeof graphEdges)[]) {
        documentedEdges.push(key)
        const edge = graphEdges[key]
        expect(edge.color).toBe(color)
        expect(edge.line).toBe(line!.split(',')[0])
        expect('arrow' in edge && edge.arrow).toBe(line!.includes('arrow'))
        for (const mode of ['light', 'dark'] as const) {
          const theme = themes[mode]
          const expected = color!.startsWith('node-')
            ? theme.nodes[color!.slice(5) as keyof typeof theme.nodes]
            : theme.colors[color as keyof typeof theme.colors]
          expect(theme.edges[key]).toBe(expected)
        }
      }
    }
    expect(documentedEdges.sort()).toEqual(Object.keys(graphEdges).sort())

    const ratings = [
      ...section('Color — review ratings').matchAll(/`(\w+)`\s*=\s*(\w+)/g),
    ]
    expect(ratings).toHaveLength(Object.keys(ratingAliases).length)
    for (const [, rating, color] of ratings) {
      const key = rating as keyof typeof ratingAliases
      expect(ratingAliases[key]).toBe(color)
      for (const mode of ['light', 'dark'] as const)
        expect(themes[mode].ratings[key]).toBe(themes[mode].colors[color as keyof typeof themes.light.colors])
    }
  })

  it('matches font families, sizes, weights, and line heights', () => {
    const lines = rows('Typography')
    const fontRows = lines.filter(([label]) => label!.startsWith('`font-'))
    expect(fontRows).toHaveLength(Object.keys(typography.font).length)
    for (const [label, value] of fontRows) {
      const key = names(label!)[0]!.slice(5) as keyof typeof typography.font
      expect(typography.font[key]).toBe(names(value!)[0])
    }

    const sizeRows = lines.filter(([, uno]) => uno?.startsWith('`text-'))
    expect(sizeRows).toHaveLength(Object.keys(typography.size).length)
    for (const [label, , value] of sizeRows) {
      const key = names(label!)[0]! as keyof typeof typography.size
      const [rem, px] = documentedNumbers(value!)
      expect(typography.size[key]).toBe(`${rem}rem`)
      expect(rem! * 16).toBe(px)
    }

    const text = section('Typography')
    const weights = [
      ...text.matchAll(/(\d+) (regular|medium|semibold|bold)/g),
    ]
    expect(weights).toHaveLength(Object.keys(typography.weight).length)
    for (const [, value, name] of weights)
      expect(typography.weight[name as keyof typeof typography.weight]).toBe(value)
    const heights = [
      ...text.matchAll(/`(tight|normal|relaxed)` (\d+\.\d+)/g),
    ]
    expect(heights).toHaveLength(Object.keys(typography.lineHeight).length)
    for (const [, name, value] of heights)
      expect(typography.lineHeight[name as keyof typeof typography.lineHeight]).toBe(value)
  })

  it('matches all spacing, radius, shadow, and motion values', () => {
    const text = section('Spacing')
    const allowed = /Allowed steps: `([^`]+)`/.exec(text)![1]!.split('·').map(value => value.trim().match(/^\d+(?:\.\d+)?/)![0])
    expect(Object.keys(spacing).sort()).toEqual(allowed.sort())
    for (const [, step, px] of text.matchAll(/(\d+(?:\.\d+)?)\s*\((\d+)(?:px)?\)/g))
      expect(spacing[Number(step) as keyof typeof spacing]).toBe(`${px}px`)
    expect(spacing[0]).toBe('0')
    const recommendations = names(text.slice(text.indexOf('Page padding:')))
    expect(layout.pagePadding.mobile).toBe(spacing[Number(recommendations[0]!.slice(2)) as keyof typeof spacing])
    expect(layout.pagePadding.lg).toBe(spacing[Number(recommendations[1]!.slice(2)) as keyof typeof spacing])
    expect(layout.navigationBreakpoint).toBe(layout.breakpoints[recommendations[2] as keyof typeof layout.breakpoints])
    expect(layout.sectionGap).toBe(spacing[Number(recommendations[3]!.slice(4)) as keyof typeof spacing])
    expect(layout.cardGap).toBe(spacing[Number(recommendations[4]!.slice(4)) as keyof typeof spacing])

    const shapeRows = rows('Shape, elevation, motion')
    const reduced = /sets the durations to (\d+)/.exec(section('Shape, elevation, motion'))![1]
    expect(motion.reducedDuration).toBe(`${reduced}ms`)
    for (const [label, value] of shapeRows) {
      const token = names(label!)[0]!
      if (token.startsWith('radius-'))
        expect(radius[token.slice(7) as keyof typeof radius]).toBe(value)
      if (token.startsWith('shadow-')) {
        const key = token.slice(7) as '1' | '2'
        const light = names(value!)[0]!
        expect(shadows.light[key]).toBe(light)
        const dark = shadows.dark[key]
        const lightAlphas = [
          ...light.matchAll(/\/\s*(\.\d+)/g),
        ]
        const darkAlphas = [
          ...dark.matchAll(/\/\s*(\.\d+)/g),
        ]
        expect(dark.replace(/\/\s*\.\d+/g, '/ alpha')).toBe(light.replace(/\/\s*\.\d+/g, '/ alpha'))
        expect(darkAlphas).toHaveLength(lightAlphas.length)
        lightAlphas.forEach((alpha, index) =>
          expect(Number(darkAlphas[index]![1])).toBeCloseTo(Number(alpha[1]) * 3),
        )
      }
      if (token.startsWith('ease-'))
        expect(motion.easing[token.slice(5) as keyof typeof motion.easing]).toBe(names(value!)[0])
      if (token === 'duration-fast') {
        const [fast, normal, slow] = documentedNumbers(value!)
        expect(motion.duration).toEqual({ fast: `${fast}ms`, normal: `${normal}ms`, slow: `${slow}ms` })
      }
    }
  })

  it('matches every documented layout, sizing, and focus-ring dimension', () => {
    const values = Object.fromEntries(rows('Layout & sizing').map(([label, value]) => [label, value]))
    const breakpoints = [
      ...values.Breakpoints!.matchAll(/`(\w+)`\s+(\d+)/g),
    ]
    expect(Object.keys(layout.breakpoints)).toHaveLength(breakpoints.length)
    for (const [, name, px] of breakpoints)
      expect(layout.breakpoints[name as keyof typeof layout.breakpoints]).toBe(`${px}px`)
    expect(layout.headerHeight).toBe(`${documentedNumbers(values['Header height']!)[0]}px`)
    const [sidebar, collapsed] = documentedNumbers(values['Sidebar width']!)
    expect(layout.sidebarWidth).toBe(`${sidebar}px`)
    expect(layout.sidebarCollapsedWidth).toBe(`${collapsed}px`)
    expect(layout.navigationBreakpoint).toBe(layout.breakpoints[names(values['Sidebar width']!)[0] as keyof typeof layout.breakpoints])
    const [bottom] = documentedNumbers(values['Bottom nav']!)
    expect(layout.bottomNavHeight).toBe(`${bottom}px`)
    expect(layout.bottomNavWithSafeArea).toBe(`calc(${bottom}px + ${names(values['Bottom nav']!)[0]})`)
    expect(layout.navigationBreakpoint).toBe(layout.breakpoints[names(values['Bottom nav']!)[1] as keyof typeof layout.breakpoints])
    const [content, reading] = documentedNumbers(values['Content max width']!)
    expect(layout.contentMaxWidth).toBe(`${content}px`)
    expect(layout.readingMaxWidth).toBe(`${reading}px`)
    const [small, medium, large] = documentedNumbers(values['Control heights']!)
    expect(layout.controlHeight).toEqual({ small: `${small}px`, medium: `${medium}px`, large: `${large}px` })
    const [dense, defaultSize, nav] = documentedNumbers(values['Icon sizes']!)
    expect(layout.iconSize).toEqual({ dense: `${dense}px`, default: `${defaultSize}px`, nav: `${nav}px` })
    expect(layout.touchTarget).toBe(`${documentedNumbers(values['Touch target']!)[0]}px`)
    const [width, offset] = documentedNumbers(values['Focus ring']!)
    expect(layout.focusRing).toEqual({ width: `${width}px`, style: 'solid', offset: `${offset}px` })
    expect(values['Focus ring']).toContain('solid')
  })
})
