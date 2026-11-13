// @vitest-environment node

import { join } from 'node:path'
import process from 'node:process'
import { ESLint } from 'eslint'
import { describe, expect, it } from 'vitest'

const eslint = new ESLint({
  cwd: process.cwd(),
})

async function tokenMessages(source: string) {
  const [result] = await eslint.lintText(source, {
    filePath: join('src', 'design', 'TokenFixture.vue'),
  })
  expect(result?.fatalErrorCount).toBe(0)
  return result!.messages.filter(message =>
    message.ruleId?.startsWith('pandawords/') || message.ruleId === 'unocss/blocklist',
  )
}

describe('token enforcement', () => {
  it('rejects hex, rgb, and pixel literals in SFC declarations, media queries, and inline styles', async () => {
    const messages = await tokenMessages(`
      <template>
        <div style="color: #fff; width: 13px; background: RGB(0 0 0)" />
      </template>
      <style scoped>
        .sample { color: #AABBCC; padding: 1.5px; background: rgba(0, 0, 0, .5); }
        @media (min-width: 13px) { .sample { display: block; } }
      </style>
    `)
    expect(messages).toHaveLength(7)
    expect(messages.every(message => message.ruleId === 'pandawords/no-raw-style-values')).toBe(true)
  }, 20_000)

  it('checks dynamic style objects, CSS strings, implicit pixels, and constant concatenation', async () => {
    const messages = await tokenMessages(`
      <template>
        <div
          :style="{ color: '#fff', width: 13, height: '1' + '3px', background: 'rgb(0 0 0)' }"
          v-bind="{ style: 'border: 2px solid #fff' }"
        />
      </template>
    `)
    expect(messages).toHaveLength(5)
    expect(messages.some(message => message.message.includes('implicit px'))).toBe(true)
  })

  it('catches negative, conditional, and kebab-case implicit pixel dimensions without rejecting unitless values', async () => {
    const messages = await tokenMessages(`
      <template>
        <div :style="{ width: active ? -13 : 10 + 3, 'margin-top': 5, opacity: .5 }" />
      </template>
    `)
    expect(messages).toHaveLength(3)
    expect(messages.every(message => message.message.includes('implicit px'))).toBe(true)
  })

  it('rejects non-token font sizes even when they use relative units', async () => {
    const messages = await tokenMessages(`
      <template>
        <div
          style="font-size: 12pt"
          :style="{ fontSize: active ? '1.2em' : 'var(--pw-font-size-sm)', font: 'bold 1em sans-serif' }"
        />
      </template>
      <style>
        .sample { font-size: 1.1rem; }
        .shorthand { font: italic 1.1rem/1.5 var(--pw-font-sans); }
        .allowed { font-size: var(--pw-font-size-base); }
      </style>
    `)
    expect(messages).toHaveLength(5)
    expect(messages.every(message => message.message.includes('font-size'))).toBe(true)
  })

  it('allows one explicitly justified declaration or bound value per exception comment', async () => {
    const messages = await tokenMessages(`
      <template>
        <div
          style="/* token-exception: imported logo geometry */ width: 13px; color: var(--pw-color-text)"
          :style="{ width: /* token-exception: external chart API */ '13px' }"
        />
      </template>
      <style>
        .sample {
          /* token-exception: third-party diagram geometry */
          width: 13px;
          /* token-exception: preserve a brand asset */
          color: #fff;
        }
      </style>
    `)
    expect(messages).toEqual([])
  })

  it('rejects empty or misplaced exceptions and does not let one exception excuse later values', async () => {
    const messages = await tokenMessages(`
      <template>
        <div
          style="/* token-exception: */ width: 13px; /* token-exception: one value */ height: 13px; color: #fff"
          :style="{ width: /* token-exception: */ -13 }"
        />
      </template>
      <style>
        /* token-exception: applies to the selector, not its declarations */
        .sample { color: #fff; }
      </style>
    `)
    expect(messages).toHaveLength(4)
  })

  it('limits an at-rule exception to the at-rule, not declarations inside it', async () => {
    const messages = await tokenMessages(`
      <template><div /></template>
      <style>
        /* token-exception: imported widget breakpoint */
        @media (min-width: 13px) { .widget { width: 13px; } }
      </style>
    `)
    expect(messages).toHaveLength(1)
    expect(messages[0]?.message).toContain('13px')
  })

  it('does not let an empty exception span an unrelated comment in a bound style', async () => {
    const messages = await tokenMessages(`
      <template>
        <div :style="{ width: /* token-exception: */ '13px', color: /* unrelated */ '#fff' }" />
      </template>
    `)
    expect(messages).toHaveLength(2)
  })

  it('ignores comments, quoted content, URLs, and values using token variables', async () => {
    const messages = await tokenMessages(`
      <template><div style="color: var(--pw-color-text); width: var(--pw-space-4)" /></template>
      <style>
        /* A historical value was #fff and 13px. */
        #abc { content: "#fff 13px"; background-image: url("asset-13px.svg"); color: var(--pw-color-text); }
      </style>
    `)
    expect(messages).toEqual([])
  })

  it('fails lint on arbitrary, default-palette, non-token scale and raw-value utilities', async () => {
    for (const name of [
      'p-[13px]',
      'bg-red-500',
      'hover:bg-red-500',
      'p-5',
      'p5',
      'pa-5',
      'gap-col-5',
      'translate-5',
      'p-13px',
      'p13px',
      'bg-hex-fff',
      'text-#fff',
      'text-4xl',
      'leading-8',
      'font-800',
      'rounded-xl',
      'shadow-lg',
      'focus-visible:ring-3',
      'duration-150ms',
    ]) {
      const messages = await tokenMessages(`<template><div class="${name}" /></template>`)
      expect(messages.some(message => message.ruleId === 'unocss/blocklist'), name).toBe(true)
    }
  })

  it('rejects blocked classes in bound class arrays, objects, templates and v-bind objects', async () => {
    const messages = await tokenMessages(`
      <template>
        <div :class="['p-[13px]', { 'bg-red-500': active }, \`w-[\${width}px]\`]" />
        <div v-bind="{ class: 'gap-5' }" />
      </template>
    `)
    expect(messages.filter(message => message.ruleId === 'pandawords/no-blocked-dynamic-classes')).toHaveLength(4)
  })

  it('accepts documented utilities and does not let style exceptions exempt blocked classes', async () => {
    expect(await tokenMessages(
      '<template><div class="p-4 lg:p-6 bg-primary text-fg rounded-md shadow-1 focus-visible:pw-focus-ring" :class="{ \'gap-3\': active }" /></template>',
    )).toEqual([])
    const messages = await tokenMessages(
      '<template><div class="p-[13px]" style="/* token-exception: external widget */ width: 13px" /></template>',
    )
    expect(messages.some(message => message.ruleId === 'unocss/blocklist')).toBe(true)
  })
})
