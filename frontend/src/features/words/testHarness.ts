import type { components } from '@/api/schema'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia } from 'pinia'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { createAppI18n } from '@/i18n'
import LemmaDetailPage from './LemmaDetailPage.vue'

export const base: components['schemas']['DictionaryEntryRead'] = {
  lemma: {
    id: 'lemma:opaque',
    owner: null,
    table: 'lemma',
    fields: { text: 'run', kind: 'word' },
  },
  lexemes: [
    {
      lexeme: {
        id: 'lexeme:opaque',
        owner: null,
        table: 'lexeme',
        fields: {
          pos: 'verb',
          pron: [
            { accent: 'US', ipa: 'rʌn' },
          ],
        },
      },
      senses: [
        {
          id: 'sense:opaque',
          owner: null,
          table: 'sense',
          fields: {
            definition: 'Move quickly',
            gloss: { zh: '跑', fr: 'courir' },
          },
        },
      ],
    },
  ],
}
let dispose: (() => void) | undefined
export function cleanup() {
  dispose?.()
}
export function ok(data: unknown) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
export function fail(status = 500, field?: string) {
  return {
    error: { code: 'unknown.private', message: 'SECRET SERVER TEXT', field },
    response: new Response(null, { status }),
  }
}
export function button(label: string) {
  const element = [
    ...document.body.querySelectorAll('button'),
  ].find(node => node.textContent?.trim() === label)
  if (!element)
    throw new Error(`Missing button ${label}`)
  return new DOMWrapper(element)
}
export async function setup(locale: 'en' | 'zh-CN' = 'en', wait = true) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/words/:lemmaId', name: 'word', component: LemmaDetailPage },
      {
        path: '/tags',
        name: 'tags',
        component: { template: '<p>Tags</p>' },
      },
      {
        path: '/projects/:id',
        name: 'project',
        component: { template: '<p>Project</p>' },
      },
    ],
  })
  await router.push({
    name: 'word',
    params: { lemmaId: base.lemma.id },
  })
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(defineComponent({
    setup: () => () => h(NConfigProvider, null, {
      default: () => h(NMessageProvider, null, {
        default: () => h(RouterView),
      }),
    }),
  }), {
    attachTo: document.body,
    global: {
      plugins: [
        router,
        i18n,
        createPinia(),
      ],
    },
  })
  dispose = () => wrapper.unmount()
  if (wait)
    await flushPromises()
  return { wrapper, router }
}
