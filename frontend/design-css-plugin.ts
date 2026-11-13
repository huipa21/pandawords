import type { Declaration } from 'postcss'
import type { Plugin } from 'vite'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import postcss from 'postcss'
import { generateTokenCss } from './src/design/css-vars.ts'
import { typography } from './src/design/tokens.ts'

const require = createRequire(import.meta.url)
const virtualId = 'virtual:pw-design.css'
const resolvedId = `\0${virtualId}`
const fonts = [
  { package: 'roboto', family: typography.font.sans },
  { package: 'roboto-serif', family: typography.font.serif },
  { package: 'noto-sans', family: typography.font.ipa },
  { package: 'roboto-mono', family: typography.font.mono },
]

export function generateFontCss() {
  return fonts.map(({ package: name, family }) => {
    const packageName = `@fontsource-variable/${name}`
    const source = readFileSync(require.resolve(`${packageName}/index.css`), 'utf8')
    const root = postcss.parse(source)
    let count = 0

    root.walkComments((comment) => {
      comment.remove()
    })
    root.walkAtRules('font-face', (face) => {
      const src = face.nodes?.find((node): node is Declaration => node.type === 'decl' && node.prop === 'src')
      if (!src || !new RegExp(`${name}-latin(?:-ext)?-wght-normal\\.woff2`).test(src.value)) {
        face.remove()
        return
      }

      const familyDeclaration = face.nodes?.find((node): node is Declaration => node.type === 'decl' && node.prop === 'font-family')
      const familyName = /^"([^"]+)"/.exec(family)?.[1]
      if (!familyDeclaration || !familyName)
        throw new Error(`Missing font family for ${packageName}`)

      familyDeclaration.value = `"${familyName}"`
      src.value = src.value.replace('./files/', `${packageName}/files/`)
      count++
    })
    if (count !== 2)
      throw new Error(`Expected Latin and Latin-ext subsets for ${packageName}`)
    return root.toString()
  }).join('\n')
}

export function fontLicenseAssets() {
  return fonts.map(({ package: name }) => ({
    type: 'asset' as const,
    fileName: `font-license-${name}.txt`,
    source: readFileSync(require.resolve(`@fontsource-variable/${name}/LICENSE`), 'utf8'),
  }))
}

export function designCssPlugin(): Plugin {
  return {
    name: 'pandawords-design-css',
    resolveId: id => id === virtualId
      ? resolvedId
      : undefined,
    load: id => id === resolvedId
      ? `${generateFontCss()}\n${generateTokenCss()}`
      : undefined,
    generateBundle() {
      for (const asset of fontLicenseAssets())
        this.emitFile(asset)
    },
  }
}
