import { gzipSync } from 'node:zlib'
import { describe, expect, it } from 'vitest'
import { analyze, analyzePrecache, budgets, enforce } from '../../bundle-budget'

const project = 'src/features/projects/ProjectPage.vue'
const graph = 'src/features/graph/GraphExplorer.vue'
const shell = 'src/components/app/AppShell.vue'

function fixture() {
  const contents = new Uint8Array(2048).fill(97)
  const short = new TextEncoder().encode('short')
  const report = analyze({
    'entry': {
      file: 'entry.js',
      isEntry: true,
      imports: ['shared'],
      dynamicImports: [project, shell],
      css: ['app.css'],
    },
    'shared': {
      file: 'shared.js',
      css: ['app.css'],
    },
    [shell]: {
      file: 'shell.js',
      imports: ['shared'],
    },
    [project]: {
      file: 'project.js',
      imports: ['shared'],
      dynamicImports: [graph],
    },
    [graph]: {
      file: 'graph.js',
      imports: ['shared'],
      css: ['graph.css'],
    },
    'src/features/graph/AllWordsPage.vue': {
      file: 'words.js',
      imports: [graph],
    },
    'src/features/auth/LoginPage.vue': {
      file: 'short.js',
      imports: ['shared'],
    },
  }, file => file === 'short.js' || file === 'boot.js'
    ? short
    : contents, `
    <script type="module" src="/entry.js"></script>
    <script src="/boot.js"></script>
    <link rel="modulepreload" href="/shared.js">
    <link rel="stylesheet" href="/app.css">
  `)
  return { report, contents, short }
}

describe('production gzip budget', () => {
  it('counts shared static dependencies once and includes layouts and only the selected lazy views', () => {
    const { report, contents, short } = fixture()
    const gzip = gzipSync(contents, { level: 1 }).byteLength
    const tree = report.routes.find(route => route.route === project)!
    const graphRoute = report.routes.find(route => route.route === `${project}#graph`)!
    const login = report.routes.find(route => route.route.endsWith('/LoginPage.vue'))!
    expect(report.initialJs).toBe(gzip * 2 + gzipSync(short, { level: 1 }).byteLength)
    expect(report.initialJsTransfer).toBe(gzip * 2 + short.byteLength)
    expect(report.initialCss).toBe(gzip)
    expect(tree.gzipBytes).toBe(gzip * 4 + gzipSync(short, { level: 1 }).byteLength)
    expect(tree.files).not.toContain('graph.js')
    expect(graphRoute.gzipBytes).toBe(gzip * 5 + gzipSync(short, { level: 1 }).byteLength)
    expect(graphRoute.cssGzipBytes).toBe(gzip * 2)
    expect(login.transferBytes).toBe(gzip * 2 + short.byteLength * 2)
    expect(report.chunks.find(chunk => chunk.file === 'graph.js')?.initial).toBe(false)
  })

  it('fails closed on broken manifests, missing routes and exceeded budgets', () => {
    const { report } = fixture()
    expect(() => analyze({}, () => new Uint8Array())).toThrow('No entry')
    expect(() => analyze({
      entry: {
        file: 'x.js',
        isEntry: true,
        imports: ['missing'],
      },
    }, () => new Uint8Array())).toThrow('Missing')
    expect(() => analyze({
      entry: { file: 'x.js', isEntry: true },
    }, () => new Uint8Array(), '<script src="https://example.test/script.js"></script>')).toThrow('Unsupported')
    expect(() => enforce(report)).not.toThrow()
    expect(() => enforce({ ...report, initialJsTransfer: budgets.initialJs + 1 })).toThrow('Initial')
    expect(() => enforce({ ...report, initialCssTransfer: budgets.initialCss + 1 })).toThrow('Initial')
    expect(() => enforce({
      ...report,
      chunks: [
        {
          file: 'lazy.js',
          initial: false,
          gzipBytes: 0,
          transferBytes: budgets.chunk + 1,
        },
      ],
    })).toThrow('chunk')
    expect(() => enforce({ ...report, staticJsTransfer: budgets.staticJs + 1 })).toThrow('static JavaScript')
    expect(() => enforce({ ...report, routes: [] })).toThrow('Missing budgeted route')
    const oversized = report.routes.map(route => route.route === project
      ? { ...route, transferBytes: budgets.projectTree + 1 }
      : route)
    expect(() => enforce({ ...report, routes: oversized })).toThrow(project)
  })

  it('reports precache transfer separately, leaves fonts uncompressed and enforces its budget', () => {
    const { report, contents, short } = fixture()
    const precache = analyzePrecache([
      { url: '/index.html' },
      { url: '/assets/app.js' },
      { url: '/assets/font.woff2' },
      { url: '/boot.js' },
    ], file => file === 'boot.js'
      ? short
      : contents)
    const gzip = gzipSync(contents, { level: 1 }).byteLength
    expect(precache.count).toBe(4)
    expect(precache.rawBytes).toBe(contents.byteLength * 3 + short.byteLength)
    expect(precache.transferBytes).toBe(gzip * 2 + contents.byteLength + short.byteLength)
    expect(precache.categories.fonts?.transferBytes).toBe(contents.byteLength)
    expect(() => enforce(report, precache)).not.toThrow()
    expect(() => enforce(report, { ...precache, transferBytes: budgets.precache + 1 })).toThrow('PWA precache')
    expect(() => analyzePrecache([
      { url: '/x' },
      { url: '/x' },
    ], () => short)).toThrow('duplicate')
    expect(() => analyzePrecache([
      { url: '/../private' },
    ], () => short)).toThrow('Unsupported')
  })
})
