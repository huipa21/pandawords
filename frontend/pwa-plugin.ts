import type { Plugin } from 'vite'
import { createHash } from 'node:crypto'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

export function pwaPlugin(): Plugin {
  const workerFile = fileURLToPath(new URL('pwa/worker.js', import.meta.url))
  return {
    name: 'pandawords-static-pwa',
    apply: 'build',
    enforce: 'post',
    // Rolldown finalizes chunk references after generateBundle; hash the written bytes.
    writeBundle(options, bundle) {
      if (!options.dir)
        throw new Error('PWA build requires an output directory')
      const outputDir = options.dir
      const files = new Map<string, Uint8Array>()
      const include = (name: string) => {
        files.set(`/${name}`, readFileSync(join(outputDir, ...name.split('/'))))
      }
      for (const name of Object.keys(bundle)) {
        if (name === 'index.html') {
          include(name)
        }
        else if (/^assets\/.+\.(?:js|css|woff2?|png|svg|webp)$/.test(name)) {
          if (!/-[\w-]{8,}\.\w+$/.test(name))
            throw new Error(`PWA asset must have a content-versioned filename: ${name}`)
          include(name)
        }
      }
      for (const name of [
        'manifest.v1.webmanifest',
        'pwa-install.v1.js',
        'icons/panda.v1.192.png',
        'icons/panda.v1.512.png',
      ]) {
        include(name)
      }
      if (!files.has('/index.html'))
        throw new Error('PWA build requires the static index.html shell')
      const worker = readFileSync(workerFile, 'utf8')
      const precache = [...files].sort(([a], [b]) => a.localeCompare(b)).map(([url, content]) => ({
        url,
        integrity: `sha256-${createHash('sha256').update(content).digest('base64')}`,
      }))
      const version = createHash('sha256').update(worker).update(JSON.stringify(precache)).digest('hex').slice(0, 20)
      writeFileSync(join(outputDir, 'sw.js'), worker.replace('__PW_VERSION__', version)
        .replace('__PW_PRECACHE__', JSON.stringify(precache)))
    },
  }
}
