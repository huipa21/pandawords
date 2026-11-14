import type { RouteRecordRaw, RouterHistory } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'
import AppShell from '@/components/app/AppShell.vue'
import { useAuthStore } from '@/stores/auth'
import AuthLayout from './layouts/AuthLayout.vue'

const placeholder = () => import('./pages/PlaceholderPage.vue')

const pages = [
  ['words', 'words', 'words'],
  ['reading/:passageId', 'reading', 'reading'],
  ['settings', 'settings', 'settings'],
  ['admin/backup', 'admin-backup', 'backup'],
] as const

export function createAppRouter(history: RouterHistory = createWebHistory()) {
  const children: RouteRecordRaw[] = [
    { path: '', redirect: '/projects' },
    {
      path: 'projects/:id/review',
      name: 'project-review',
      component: () => import('@/features/study/ReviewSessionPage.vue'),
      meta: { title: 'review' },
    },
    {
      path: 'projects/:id/plan',
      name: 'project-plan',
      component: () => import('@/features/study/ProjectPlanPage.vue'),
      meta: { title: 'plan' },
    },
    {
      path: 'review',
      name: 'review',
      component: () => import('@/features/study/DashboardPage.vue'),
      meta: { title: 'review' },
    },
    {
      path: 'words/:lemmaId',
      name: 'word',
      component: () => import('@/features/words/LemmaDetailPage.vue'),
      meta: { title: 'word' },
    },
    {
      path: 'projects',
      name: 'projects',
      component: () => import('@/features/projects/ProjectsPage.vue'),
      meta: { title: 'projects' },
    },
    {
      path: 'projects/new',
      name: 'project-create',
      component: () => import('@/features/projects/ProjectEditorPage.vue'),
      meta: { title: 'projectCreate' },
    },
    {
      path: 'projects/:id/edit',
      name: 'project-edit',
      component: () => import('@/features/projects/ProjectEditorPage.vue'),
      meta: { title: 'projectEdit' },
    },
    {
      path: 'projects/:id',
      name: 'project',
      component: () => import('@/features/projects/ProjectPage.vue'),
      meta: { title: 'project' },
    },
    {
      path: 'admin/users',
      name: 'admin-users',
      component: () => import('@/features/admin/AdminUsersPage.vue'),
      meta: { title: 'users', admin: true },
    },
    ...pages.map(([path, name, title]) => ({
      path,
      name,
      component: placeholder,
      meta: {
        title,
        admin: path.startsWith('admin/'),
      },
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
  const router = createRouter({
    history,
    routes: [
      {
        path: '/login',
        component: AuthLayout,
        children: [
          {
            path: '',
            name: 'login',
            component: () => import('@/features/auth/LoginPage.vue'),
            meta: { title: 'login' },
          },
        ],
      },
      {
        path: '/change-password',
        component: AuthLayout,
        children: [
          {
            path: '',
            name: 'change-password',
            component: () => import('@/features/auth/ChangePasswordPage.vue'),
            meta: { title: 'changePassword', authenticated: true },
          },
        ],
      },
      {
        path: '/',
        component: AppShell,
        meta: { authenticated: true },
        children,
      },
    ],
    scrollBehavior: () => ({ top: 0 }),
  })
  router.beforeEach(async (to) => {
    const auth = useAuthStore()
    await auth.restore()
    if (!auth.accessToken) {
      return to.name === 'login'
        ? true
        : { name: 'login' }
    }
    if (auth.user?.must_change_password) {
      return to.name === 'change-password'
        ? true
        : { name: 'change-password' }
    }
    if (to.name === 'login')
      return { name: 'projects' }
    if (to.meta.admin && !auth.isAdmin)
      return { name: 'projects' }
    return true
  })
  return router
}
