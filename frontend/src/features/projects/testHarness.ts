import type { components } from '@/api/schema'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { themeOverrides } from '@/design/naive-theme'
import { createAppI18n } from '@/i18n'
import ProjectEditorPage from './ProjectEditorPage.vue'
import ProjectPage from './ProjectPage.vue'
import ProjectsPage from './ProjectsPage.vue'

export const project: components['schemas']['ProjectRead'] = {
  id: 'project:sample',
  name: 'Exam vocabulary',
  description: 'Study together',
  source_lang: 'zh',
  target_lang: 'en',
  plan: { daily_new: 20, review_cap: 50, exam_date: '2027-01-02T03:04:05Z' },
  created_at: '2026-11-14T00:00:00Z',
}
export function success(data: unknown) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
export function failure(code: string, field: string | null = null, status = 400) {
  return {
    error: { code, field, message: 'NEVER DISPLAY RAW SERVER TEXT' },
    response: new Response(null, { status }),
  }
}
export function list(items = [project], page = 1, total = items.length) {
  return success({ items, page, total, page_size: 20 })
}
export async function setup(path = '/projects', locale: 'en' | 'zh-CN' = 'en') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects', name: 'projects', component: ProjectsPage },
      { path: '/projects/new', name: 'project-create', component: ProjectEditorPage },
      { path: '/projects/:id/edit', name: 'project-edit', component: ProjectEditorPage },
      { path: '/projects/:id', name: 'project', component: ProjectPage },
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
      plugins: [router, i18n],
    },
  })
  await flushPromises()
  return {
    wrapper,
    router,
    cleanup: () => {
      wrapper.unmount()
      root.remove()
    },
  }
}
export function button(text: string) {
  const element = Array.from(document.body.querySelectorAll('button')).find(button => button.textContent?.trim() === text)
  if (!element)
    throw new Error(`Missing button: ${text}`)
  return new DOMWrapper(element)
}
