import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider, NMessageProvider } from 'naive-ui'
import { createPinia, disposePinia } from 'pinia'
import { afterEach, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import { AuthRequestError } from './errors'
import ProfileAvatar from './ProfileAvatar.vue'
import ProfilePage from './ProfilePage.vue'
import { authPayload } from './testHarness'

const wrappers: ReturnType<typeof mount>[] = []
const instances: ReturnType<typeof createPinia>[] = []
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  instances.splice(0).forEach(disposePinia)
  vi.restoreAllMocks()
})

async function render() {
  const pinia = createPinia()
  instances.push(pinia)
  const auth = useAuthStore(pinia)
  auth.accessToken = 'test-access'
  auth.user = authPayload({ full_name: 'Alice Brown', email: 'alice@example.com', avatar: '' }).user
  const router = createRouter({
    history: createMemoryHistory(),
    routes: ['/profile', '/projects'].map(path => ({
      path,
      component: { template: '<div />' },
    })),
  })
  await router.push('/profile')
  const i18n = createAppI18n()
  i18n.global.locale.value = 'en'
  const root = defineComponent({
    setup: () => () => h(NConfigProvider, null, {
      default: () => h(NMessageProvider, null, {
        default: () => h(ProfilePage),
      }),
    }),
  })
  const wrapper = mount(root, {
    global: {
      plugins: [pinia, router, i18n],
    },
  })
  wrappers.push(wrapper)
  return { wrapper, auth, router }
}

it('keeps identity read-only, validates email and preserves failed drafts before retrying', async () => {
  const { wrapper, auth } = await render()
  expect(wrapper.get('#profile-id').attributes()).toHaveProperty('readonly')
  expect(wrapper.get('#profile-username').attributes()).toHaveProperty('readonly')
  expect(wrapper.getComponent(ProfileAvatar).text()).toBe('AB')
  const update = vi.spyOn(auth, 'updateProfile')
    .mockRejectedValueOnce(new AuthRequestError({ code: 'transport', field: null, message: '' }))
    .mockImplementationOnce(async (data) => {
      auth.user = {
        ...auth.user!,
        ...data,
      }
    })
  await wrapper.get('#profile-email').setValue('not-email')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(update).not.toHaveBeenCalled()
  expect(wrapper.text()).toContain('Enter a valid email address.')
  await wrapper.get('#profile-email').setValue('updated@example.com')
  await wrapper.get('#profile-name').setValue('Updated Name')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(document.body.textContent).toContain('Cannot reach the server')
  expect((wrapper.get('#profile-name').element as HTMLInputElement).value).toBe('Updated Name')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(update).toHaveBeenLastCalledWith({ email: 'updated@example.com', full_name: 'Updated Name', avatar: '' })
  expect(auth.user?.full_name).toBe('Updated Name')
})

it('rejects unsupported avatars and changes the password without leaving Profile', async () => {
  const { wrapper, auth, router } = await render()
  const file = wrapper.get('#profile-avatar')
  Object.defineProperty(file.element, 'files', {
    value: [
      new File(['svg'], 'avatar.svg', { type: 'image/svg+xml' }),
    ],
  })
  await file.trigger('change')
  await flushPromises()
  expect(document.body.textContent).toContain('Choose a PNG, JPEG or WebP')
  expect(wrapper.getComponent(ProfileAvatar).props('avatar')).toBe('')
  const submitted: { current_password: string, new_password: string }[] = []
  vi.spyOn(auth, 'changePassword').mockImplementation(async (data) => {
    submitted.push({ ...data })
  })
  await wrapper.get('#current_password').setValue('old-password')
  await wrapper.get('#new_password').setValue('new-password')
  await wrapper.findAll('form')[1]!.trigger('submit')
  await flushPromises()
  expect(submitted).toEqual([
    { current_password: 'old-password', new_password: 'new-password' },
  ])
  expect(router.currentRoute.value.path).toBe('/profile')
  expect((wrapper.get('#new_password').element as HTMLInputElement).value).toBe('')
})
