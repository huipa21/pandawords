import { existsSync, readFileSync } from 'node:fs'
import { extname, resolve } from 'node:path'
import process from 'node:process'
import { pathToFileURL } from 'node:url'
import { gzipSync } from 'node:zlib'

interface Chunk {
  file: string
  imports?: string[]
  dynamicImports?: string[]
  css?: string[]
  isEntry?: boolean
}

const PROJECT = 'src/features/projects/ProjectPage.vue'
const GRAPH = 'src/features/graph/GraphExplorer.vue'
const APP_LAYOUT = 'src/components/app/AppShell.vue'
const AUTH_LAYOUT = 'src/app/layouts/AuthLayout.vue'
const ALL_WORDS = 'src/features/graph/AllWordsPage.vue'
const LOGIN = 'src/features/auth/LoginPage.vue'

export const budgets = {
  initialJs: 185_500,
  initialCss: 4_800,
  chunk: 225_000,
  staticJs: 675_000,
  projectTree: 258_000,
  projectGraph: 525_000,
  allWords: 485_000,
  login: 215_000,
  precache: 1_160_000,
}

function transferBytes(bytes: Uint8Array, extension: string) {
  const compressible = ['.js', '.css', '.html', '.svg'].includes(extension)
  return compressible && bytes.byteLength >= 1024
    ? gzipSync(bytes, { level: 1 }).byteLength
    : bytes.byteLength
}

export function analyzePrecache(entries: { url: string }[], read: (file: string) => Uint8Array) {
  const categories: Record<string, { count: number, rawBytes: number, transferBytes: number }> = {}
  const seen = new Set<string>()
  for (const { url } of entries) {
    if (typeof url !== 'string' || !url.startsWith('/') || url.startsWith('//')
      || /[?#\\]/.test(url) || url.split('/').includes('..') || seen.has(url)) {
      throw new Error(`Unsupported or duplicate precache URL: ${url}`)
    }
    seen.add(url)
    const file = url.slice(1)
    const extension = extname(file).toLowerCase()
    const category = extension === '.js'
      ? 'javascript'
      : extension === '.css'
        ? 'css'
        : ['.woff', '.woff2'].includes(extension)
            ? 'fonts'
            : ['.png', '.webp', '.svg'].includes(extension)
                ? 'images'
                : extension === '.html'
                  ? 'html'
                  : 'other'
    const bytes = read(file)
    const bucket = categories[category] ??= { count: 0, rawBytes: 0, transferBytes: 0 }
    bucket.count++
    bucket.rawBytes += bytes.byteLength
    bucket.transferBytes += transferBytes(bytes, extension)
  }
  const groups = Object.values(categories)
  return {
    count: seen.size,
    rawBytes: groups.reduce((sum, group) => sum + group.rawBytes, 0),
    transferBytes: groups.reduce((sum, group) => sum + group.transferBytes, 0),
    categories,
  }
}

export function analyze(manifest: Record<string, Chunk>, read: (file: string) => Uint8Array, html = '') {
  const initial = new Set<string>()
  const initialCss = new Set<string>()
  const initialScripts = new Set<string>()
  for (const [tag, kind] of html.matchAll(/<(script|link)\b[^>]*>/gi)) {
    const source = tag.match(/\ssrc\s*=\s*(["'])(.*?)\1/i)?.[2]
    const href = tag.match(/\shref\s*=\s*(["'])(.*?)\1/i)?.[2]
    const relation = tag.match(/\srel\s*=\s*(["'])(.*?)\1/i)?.[2]?.toLowerCase()
    const asset = kind?.toLowerCase() === 'script'
      ? source
      : relation === 'stylesheet' || relation === 'modulepreload'
        ? href
        : undefined
    if (!asset)
      continue
    if (!asset.startsWith('/') || asset.startsWith('//') || /[?#\\]/.test(asset) || asset.split('/').includes('..'))
      throw new Error(`Unsupported initial asset: ${asset}`)
    if (relation === 'stylesheet')
      initialCss.add(asset.slice(1))
    else
      initialScripts.add(asset.slice(1))
  }
  const visit = (key: string, selected: Set<string>, styles: Set<string>) => {
    if (selected.has(key))
      return
    const chunk = manifest[key]
    if (!chunk)
      throw new Error(`Missing manifest chunk: ${key}`)
    selected.add(key)
    chunk.css?.forEach(file => styles.add(file))
    chunk.imports?.forEach(dependency => visit(dependency, selected, styles))
  }
  Object.entries(manifest).filter(([, chunk]) => chunk.isEntry).forEach(([key]) => visit(key, initial, initialCss))
  if (!initial.size)
    throw new Error('No entry chunk in build manifest')

  const sizes = new Map<string, { gzipBytes: number, transferBytes: number }>()
  const size = (file: string) => {
    let result = sizes.get(file)
    if (!result) {
      const bytes = read(file)
      const gzipBytes = gzipSync(bytes, { level: 1 }).byteLength
      result = {
        gzipBytes,
        transferBytes: bytes.byteLength < 1024
          ? bytes.byteLength
          : gzipBytes,
      }
      sizes.set(file, result)
    }
    return result
  }
  const measure = (selected: Set<string>, styles: Set<string>) => {
    const files = [
      ...new Set([
        ...[...selected].map(key => manifest[key]!.file).filter(file => file.endsWith('.js')),
        ...initialScripts,
      ]),
    ].sort()
    const css = [...styles].sort()
    return {
      gzipBytes: files.reduce((sum, file) => sum + size(file).gzipBytes, 0),
      transferBytes: files.reduce((sum, file) => sum + size(file).transferBytes, 0),
      cssGzipBytes: css.reduce((sum, file) => sum + size(file).gzipBytes, 0),
      cssTransferBytes: css.reduce((sum, file) => sum + size(file).transferBytes, 0),
      files,
      css,
    }
  }
  const first = measure(initial, initialCss)
  const chunks = [
    ...new Set([
      ...Object.values(manifest).map(chunk => chunk.file).filter(file => file.endsWith('.js')),
      ...initialScripts,
    ]),
  ]
    .sort()
    .map(file => ({
      file,
      initial: first.files.includes(file),
      ...size(file),
    }))
  const pages = Object.keys(manifest).filter(key => key.endsWith('Page.vue')).sort()
  const graphKey = Object.keys(manifest).find(key => key === GRAPH || key.startsWith('_GraphExplorer-'))
  const route = (key: string, graph = false) => {
    const selected = new Set(initial)
    const styles = new Set(initialCss)
    const layout = key.startsWith('src/features/auth/')
      ? AUTH_LAYOUT
      : APP_LAYOUT
    if (manifest[layout])
      visit(layout, selected, styles)
    visit(key, selected, styles)
    if (graph && graphKey)
      visit(graphKey, selected, styles)
    return {
      route: graph
        ? `${key}#graph`
        : key,
      ...measure(selected, styles),
    }
  }
  const routes = pages.map(key => route(key))
  if (manifest[PROJECT] && graphKey)
    routes.push(route(PROJECT, true))
  return {
    initialJs: first.gzipBytes,
    initialJsTransfer: first.transferBytes,
    initialCss: first.cssGzipBytes,
    initialCssTransfer: first.cssTransferBytes,
    staticJs: chunks.reduce((sum, chunk) => sum + chunk.gzipBytes, 0),
    staticJsTransfer: chunks.reduce((sum, chunk) => sum + chunk.transferBytes, 0),
    chunks,
    routes,
  }
}

export function enforce(report: ReturnType<typeof analyze>, precache?: ReturnType<typeof analyzePrecache>) {
  if (report.initialJsTransfer > budgets.initialJs || report.initialCssTransfer > budgets.initialCss)
    throw new Error(`Initial transfer budget exceeded (JS ${budgets.initialJs} / CSS ${budgets.initialCss} bytes)`)
  if (report.chunks.some(chunk => chunk.transferBytes > budgets.chunk))
    throw new Error(`Individual JavaScript chunk exceeds ${budgets.chunk} transfer bytes`)
  if (report.staticJsTransfer > budgets.staticJs)
    throw new Error(`All static JavaScript exceeds ${budgets.staticJs} transfer bytes`)
  if (precache && precache.transferBytes > budgets.precache)
    throw new Error(`PWA precache exceeds ${budgets.precache} transfer bytes`)
  for (const [name, limit] of [
    [PROJECT, budgets.projectTree],
    [`${PROJECT}#graph`, budgets.projectGraph],
    [ALL_WORDS, budgets.allWords],
    [LOGIN, budgets.login],
  ] as const) {
    const route = report.routes.find(route => route.route === name)
    if (!route)
      throw new Error(`Missing budgeted route: ${name}`)
    if (route.transferBytes > limit)
      throw new Error(`${name} exceeds ${limit} JavaScript transfer bytes`)
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const root = resolve('dist')
  const manifest = JSON.parse(readFileSync(resolve(root, '.vite', 'manifest.json'), 'utf8'))
  const report = analyze(
    manifest,
    file => readFileSync(resolve(root, file)),
    readFileSync(resolve(root, 'index.html'), 'utf8'),
  )
  const workerFile = resolve(root, 'sw.js')
  let pwa: { precache: ReturnType<typeof analyzePrecache>, worker: { rawBytes: number, transferBytes: number } } | undefined
  if (existsSync(workerFile)) {
    const worker = readFileSync(workerFile)
    const precache = worker.toString('utf8').match(/^const precache = (.+)$/m)?.[1]
    if (!precache)
      throw new Error('Cannot read PWA precache manifest from sw.js')
    const entries: unknown = JSON.parse(precache)
    if (!Array.isArray(entries))
      throw new TypeError('Invalid PWA precache manifest')
    pwa = {
      precache: analyzePrecache(entries, file => readFileSync(resolve(root, file))),
      worker: {
        rawBytes: worker.byteLength,
        transferBytes: transferBytes(worker, '.js'),
      },
    }
  }
  process.stdout.write(`${JSON.stringify({ ...report, pwa }, null, 2)}\n`)
  if (!process.argv.includes('--report-only'))
    enforce(report, pwa?.precache)
}
