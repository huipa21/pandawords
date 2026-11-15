import type { components } from '@/api/schema'
import { DOMWrapper, flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { themeOverrides } from '@/design/naive-theme'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import AdminUsersPage from './AdminUsersPage.vue'
import UserActions from './UserActions.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
}))
vi.mock('@/api/client', async original => ({
  ...await original<typeof import('@/api/client')>(),
  api: client,
}))

function user(id: string, role: 'admin' | 'user' = 'user', disabled = false): components['schemas']['UserRead'] {
  return {
    id: `user:${id}`,
    username: id,
    email: '',
    full_name: '',
    avatar: '',
    role,
    disabled,
    must_change_password: false,
    source_lang: 'zh-CN',
    target_lang: 'en',
    prefs: {
      theme: 'system',
      locale: 'en',
      accent: 'US',
      desired_retention: 0.9,
      review_images_enabled: true,
      review_audio_enabled: true,
    },
  }
}
const self = user('owner', 'admin')
const learner = user('learner')
const otherAdmin = user('other-admin', 'admin')
function success(data: unknown) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
function failure(code: string, field: string | null = null) {
  return {
    error: { code, field, message: 'NEVER DISPLAY RAW SERVER TEXT' },
    response: new Response(null, { status: 409 }),
  }
}
function list(items = [self, learner, otherAdmin], page = 1, total = 3) {
  return success({ items, page, total, page_size: 20 })
}

let cleanup: () => void
function setup(locale: 'en' | 'zh-CN' = 'en') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.user = self
  auth.accessToken = 'test-access-token'
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const root = document.createElement('div')
  document.body.append(root)
  const wrapper = mount(defineComponent({
    setup: () => () => h(NConfigProvider, { themeOverrides }, {
      default: () => h(NMessageProvider, null, {
        default: () => h(AdminUsersPage),
      }),
    }),
  }), {
    attachTo: root,
    global: {
      plugins: [pinia, i18n],
    },
  })
  cleanup = () => {
    wrapper.unmount()
    root.remove()
    disposePinia(pinia)
  }
  return wrapper.findComponent(AdminUsersPage)
}

function button(text: string, root: ParentNode = document.body) {
  const element = Array.from(root.querySelectorAll('button')).find(button => button.textContent?.trim() === text)
  expect(element, `button: ${text}`).toBeTruthy()
  return new DOMWrapper(element!)
}

beforeEach(() => {
  vi.clearAllMocks()
  client.GET.mockResolvedValue(list())
  client.POST.mockResolvedValue(success({ user: learner, temporary_password: 'temporary-created' }))
  client.PATCH.mockImplementation((_path, options) => success({
    user: {
      ...learner,
      ...options.body,
    },
    temporary_password: options.body.reset_password ? 'temporary-reset' : null,
  }))
})
afterEach(() => {
  cleanup?.()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('admin users', () => {
  it('renders loading, empty, and bilingual load errors with retry', async () => {
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise((done) => {
      resolve = done
    }))
    const page = setup('zh-CN')
    await flushPromises()
    expect(page.get('[role="status"]').attributes('aria-label')).toBe('加载中')
    resolve(failure('auth.forbidden'))
    await flushPromises()
    expect(page.text()).toContain('你没有执行此操作的权限。')
    expect(page.text()).not.toContain('NEVER DISPLAY')
    client.GET.mockResolvedValueOnce(list([]))
    await button('重试').trigger('click')
    await flushPromises()
    expect(page.text()).toContain('暂无用户。')
  })

  it('retains confirmed page and rows on pagination failure, then retries the failed page', async () => {
    client.GET.mockResolvedValueOnce(list([learner], 1, 21))
    const page = setup()
    await flushPromises()
    client.GET.mockRejectedValueOnce(new Error('offline'))
    await button('Next').trigger('click')
    await flushPromises()
    expect(page.text()).toContain('Page 1 of 2')
    expect(page.text()).toContain('learner')
    expect(page.text()).toContain('Cannot reach the server.')
    client.GET.mockResolvedValueOnce(list([otherAdmin], 2, 21))
    await button('Retry').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/admin/users', {
      params: {
        query: { page: 2, page_size: 20 },
      },
    })
    expect(page.text()).toContain('Page 2 of 2')
    expect(button('Next').attributes('disabled')).toBeDefined()
    await button('Previous').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/admin/users', {
      params: {
        query: { page: 1, page_size: 20 },
      },
    })
  })

  it('requires confirmation, cancels without mutation, and prevents self-disable/demotion', async () => {
    const page = setup()
    await flushPromises()
    const ownActions = page.findAllComponents(UserActions).find(actions => actions.props('user').id === self.id)!
    expect(ownActions.findAll('button').filter(button => button.attributes('disabled') !== undefined)).toHaveLength(2)
    const actions = page.findAllComponents(UserActions).find(actions => actions.props('user').id === learner.id)!
    await button('Disable', actions.element).trigger('click')
    await flushPromises()
    expect(client.PATCH).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('Apply this action to learner?')
    await button('Cancel').trigger('click')
    await flushPromises()
    expect(client.PATCH).not.toHaveBeenCalled()
    await button('Disable', actions.element).trigger('click')
    await flushPromises()
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(client.PATCH).toHaveBeenCalledWith('/api/admin/users/{id}', {
      params: {
        path: { id: learner.id },
      },
      body: { disabled: true, reset_password: false },
    })
    expect(page.text()).toContain('Disabled')
    await button('Enable', actions.element).trigger('click')
    await flushPromises()
    expect(client.PATCH).toHaveBeenLastCalledWith('/api/admin/users/{id}', {
      params: {
        path: { id: learner.id },
      },
      body: { disabled: false, reset_password: false },
    })
  })

  it('surfaces protected-admin conflicts and leaves confirmation open for retry or cancel', async () => {
    const page = setup()
    await flushPromises()
    client.PATCH.mockResolvedValueOnce(failure('admin.last_admin'))
    const actions = page.findAllComponents(UserActions).find(actions => actions.props('user').id === otherAdmin.id)!
    await button('Make learner', actions.element).trigger('click')
    await flushPromises()
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('The last enabled administrator cannot be disabled or demoted.')
    expect(page.findComponent(ConfirmAction).props('show')).toBe(true)
    expect(document.body.textContent).not.toContain('NEVER DISPLAY')
    expect(client.PATCH).toHaveBeenCalledWith('/api/admin/users/{id}', {
      params: {
        path: { id: otherAdmin.id },
      },
      body: { role: 'user', reset_password: false },
    })
    client.PATCH.mockRejectedValueOnce(new Error('offline'))
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Cannot reach the server.')
    expect(page.findComponent(ConfirmAction).props('show')).toBe(true)
    client.PATCH.mockResolvedValueOnce(success({
      user: { ...otherAdmin, role: 'user' },
    }))
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(page.findComponent(ConfirmAction).props('show')).toBe(false)
    expect(actions.props('user').role).toBe('user')
  })

  it('shows reset credentials after confirmation and reports denied clipboard access', async () => {
    const writeText = vi.fn().mockRejectedValueOnce(new Error('denied')).mockResolvedValueOnce(undefined)
    vi.stubGlobal('navigator', {
      clipboard: { writeText },
    })
    const page = setup()
    await flushPromises()
    const actions = page.findAllComponents(UserActions).find(actions => actions.props('user').id === learner.id)!
    await button('Reset password', actions.element).trigger('click')
    await flushPromises()
    expect(document.body.textContent).not.toContain('temporary-reset')
    await button('Confirm').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('output')?.textContent).toBe('temporary-reset')
    await button('Copy password').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Could not copy the password.')
    await button('Copy password').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenLastCalledWith('temporary-reset')
    expect(document.body.textContent).toContain('Password copied.')
    await button('Done').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('output')?.textContent).not.toContain('temporary-reset')
    expect(localStorage.length).toBe(0)
  })

  it('validates create, displays field errors, and shows generated credentials only on success', async () => {
    setup()
    await flushPromises()
    await button('Create user').trigger('click')
    await flushPromises()
    const form = new DOMWrapper(document.body.querySelector('form')!)
    await form.trigger('submit')
    await flushPromises()
    expect(client.POST).not.toHaveBeenCalled()
    expect(document.body.textContent).toContain('This field is required.')
    await new DOMWrapper(document.body.querySelector<HTMLInputElement>('#admin-username')!).setValue('new-user')
    client.POST.mockResolvedValueOnce(failure('admin.username_taken', 'username'))
    await form.trigger('submit')
    await flushPromises()
    expect(document.body.textContent).toContain('This username is already in use.')
    expect(document.body.querySelector('output')).toBeNull()
    client.POST.mockResolvedValueOnce(success({
      user: user('new-user'),
      temporary_password: 'temporary-created',
    }))
    await form.trigger('submit')
    await flushPromises()
    expect(client.POST).toHaveBeenLastCalledWith('/api/admin/users', {
      body: { username: 'new-user', role: 'user' },
    })
    expect(document.body.querySelector('output')?.textContent).toBe('temporary-created')
    expect(client.GET).toHaveBeenLastCalledWith('/api/admin/users', {
      params: {
        query: { page: 1, page_size: 20 },
      },
    })
  })
})
