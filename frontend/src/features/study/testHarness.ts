import type { components } from '@/api/schema'
import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { themeOverrides } from '@/design/naive-theme'
import { project } from '@/features/projects/testHarness'
import { createAppI18n } from '@/i18n'
import DashboardPage from './DashboardPage.vue'
import ProjectPlanPage from './ProjectPlanPage.vue'

export { button, failure, project, success } from '@/features/projects/testHarness'

export const plan: components['schemas']['StudyPlanRead'] = {
  project_id: project.id,
  as_of: '2026-11-14T01:00:00Z',
  plan: project.plan,
  due: 2,
  new: 3,
  today: { new: 4, reviews: 5 },
  remaining_new_allowance: 16,
  remaining_review_allowance: 45,
  queue: [],
  queue_total: 5,
  offset: 0,
  limit: 1,
  exam: {
    remaining_new: 3,
    days_left: 0,
    suggested_daily_new: 0,
    capacity: 0,
    buffer_capacity: 0,
    impossible: true,
    buffer_at_risk: true,
  },
  forecast: Array.from({ length: 7 }, (_, index) => ({ date: `2026-11-${14 + index}`, due: index })),
}
export const dashboard: components['schemas']['DashboardRead'] = {
  as_of: plan.as_of,
  due_today: 2,
  new_today: 3,
  today: plan.today,
  retention_30_days: null,
  streak: 0,
  forecast: plan.forecast,
  projects: [
    {
      project_id: project.id,
      name: project.name,
      due: plan.due,
      new: plan.new,
      today: plan.today,
      forecast: plan.forecast,
      exam: plan.exam,
    },
  ],
}

export function tree(ids: string[], hidden = false): components['schemas']['ProjectTreeLemmaRead'] {
  return {
    lemma: {
      id: 'lemma:test',
      table: 'lemma',
      owner: null,
      fields: { text: 'test' },
    },
    hidden,
    effective_hidden: hidden,
    lexemes: [
      {
        lexeme: {
          id: 'lexeme:test',
          table: 'lexeme',
          owner: null,
          fields: { pos: 'noun' },
        },
        hidden: false,
        effective_hidden: hidden,
        senses: ids.map(id => ({
          sense: {
            id,
            table: 'sense',
            owner: null,
            fields: { definition: `Definition ${id}` },
          },
          hidden: false,
          effective_hidden: hidden,
        })),
      },
    ],
  }
}

export async function setup(path = '/review', locale: 'en' | 'zh-CN' = 'en') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/review', name: 'review', component: DashboardPage },
      {
        path: '/projects/:id/plan',
        name: 'project-plan',
        component: path === '/review'
          ? { template: '<div />' }
          : ProjectPlanPage,
      },
      {
        path: '/projects/:id/review',
        name: 'project-review',
        component: { template: '<div />' },
      },
      {
        path: '/projects/:id',
        name: 'project',
        component: { template: '<div />' },
      },
      {
        path: '/projects',
        name: 'projects',
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
