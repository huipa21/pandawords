import type { RouteRecordRaw, RouterHistory } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '@/components/app/AppShell.vue'
import AuthLayout from './layouts/AuthLayout.vue'

const placeholder = () => import('./pages/PlaceholderPage.vue')

const pages = [
  ['projects', 'projects', 'projects'],
  ['projects/:id', 'project', 'project'],
  ['projects/:id/review', 'project-review', 'review'],
  ['projects/:id/plan', 'project-plan', 'plan'],
  ['review', 'review', 'review'],
  ['words', 'words', 'words'],
  ['words/:lemmaId', 'word', 'word'],
  ['reading/:passageId', 'reading', 'reading'],
  ['settings', 'settings', 'settings'],
  ['admin/users', 'admin-users', 'users'],
  ['admin/backup', 'admin-backup', 'backup'],
] as const

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const children: RouteRecordRaw[] = [
    { path: '', redirect: '/projects' },
    ...pages.map(([path, name, title]) => ({
      path,
      name,
      component: placeholder,
      meta: { title },
    })),
  ]
  if (import.meta.env.DEV) {
    children.push({
      path: 'dev/design',
      name: 'design',
      component: () => import('@/features/dev-design/DesignPreviewPage.vue'),
      meta: { title: 'design' },
    })
  }
  children.push({
    path: ':pathMatch(.*)*',
    name: 'not-found',
    component: placeholder,
    meta: { title: 'notFound' },
  })
  return createRouter({
    history,
    routes: [
      {
        path: '/login',
        component: AuthLayout,
        children: [
          {
            path: '',
            name: 'login',
            component: placeholder,
            meta: { title: 'login' },
          },
        ],
      },
      { path: '/', component: AppShell, children },
    ],
    scrollBehavior: () => ({ top: 0 }),
  })
}
