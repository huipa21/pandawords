import type { Component } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, setActivePinia } from 'pinia'
import { vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { themeOverrides } from '@/design/naive-theme'
import { createAppI18n } from '@/i18n'

export async function mountPage(page: Component, locale: 'en' | 'zh-CN' = 'en', path = '/page') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/page', component: page },
      {
        path: '/projects/:id',
        name: 'project',
        component: { template: '<div />' },
      },
    ],
  })
  await router.push(path)
  await router.isReady()
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const root = document.createElement('div')
  document.body.append(root)
  const wrapper = mount(defineComponent({
    setup: () => () => h(NConfigProvider, { themeOverrides }, {
      default: () => h(NMessageProvider, null, {
        default: () => h(RouterView),
      }),
    }),
  }), {
    attachTo: root,
    global: {
      plugins: [router, i18n, pinia],
    },
  })
  await flushPromises()
  return {
    wrapper,
    router,
    pinia,
    cleanup: () => {
      wrapper.unmount()
      root.remove()
    },
  }
}

export function archive(name = 'deck.pandawords-project.tar.gz', bytes = 4) {
  return new File([
    new Uint8Array(bytes),
  ], name, { type: 'application/gzip' })
}

export function query(selector: string) {
  const element = document.body.querySelector<HTMLElement>(selector)
  if (!element)
    throw new Error(`Missing element: ${selector}`)
  return element
}

export function clickText(text: string) {
  const element = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.trim() === text)
  if (!element)
    throw new Error(`Missing button: ${text}`)
  element.click()
  return flushPromises()
}

export async function chooseFile(file: File, root = document.body) {
  const input = root.querySelector<HTMLInputElement>('[data-testid="archive-input"]')!
  Object.defineProperty(input, 'files', {
    value: [file],
    configurable: true,
  })
  input.dispatchEvent(new Event('change'))
  await flushPromises()
}

export function blobResult(name: string, headers: Record<string, string> = {}) {
  return {
    data: new Blob(['archive']),
    response: new Response(null, {
      status: 200,
      headers: { 'Content-Disposition': `attachment; filename="${name}"`, ...headers },
    }),
  }
}

export function apiError(code: string, status: number, extra: Record<string, unknown> = {}) {
  return {
    error: {
      code,
      message: 'NEVER DISPLAY RAW SERVER TEXT',
      field: null,
      ...extra,
    },
    response: new Response(null, { status }),
  }
}

export function abortable() {
  return (_path: string, options: { signal: AbortSignal }) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
  })
}

/** Captures saved downloads instead of navigating. */
export function captureDownloads() {
  const saved: string[] = []
  vi.stubGlobal('URL', Object.assign(URL, {
    createObjectURL: vi.fn(() => 'blob:local'),
    revokeObjectURL: vi.fn(),
  }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved.push(this.download)
  })
  return saved
}
