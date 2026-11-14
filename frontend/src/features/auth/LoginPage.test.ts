import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, disposePinia, setActivePinia } from 'pinia'
import { expect, it, vi } from 'vitest'
import { createMemoryHistory } from 'vue-router'
import App from '@/app/App.vue'
import { createAppRouter } from '@/app/router'
import { createAppI18n } from '@/i18n'

it('validates login, shows localized field errors, and reports transport failures visibly', async () => {
  localStorage.clear()
  const fetch = vi.fn<typeof globalThis.fetch>()
    .mockResolvedValueOnce(new Response(null, { status: 401 }))
    .mockResolvedValueOnce(Response.json({
      code: 'auth.invalid_credentials',
      field: 'password',
      message: 'Do not display raw server text',
    }, { status: 401 }))
    .mockRejectedValueOnce(new Error('offline'))
  vi.stubGlobal('fetch', fetch)
  const pinia = createPinia()
  setActivePinia(pinia)
  const router = createAppRouter(createMemoryHistory())
  await router.push('/login')
  const wrapper = mount(App, {
    global: {
      plugins: [
        pinia,
        createAppI18n(),
        router,
      ],
    },
  })
  try {
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('此项不能为空。')
    await wrapper.get('#username').setValue('learner')
    await wrapper.get('#password').setValue('wrong-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('用户名或密码不正确。')
    expect(wrapper.text()).not.toContain('Do not display raw server text')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(document.body.textContent).toContain('无法连接服务器，请检查网络后重试。')
    expect(fetch).toHaveBeenCalledTimes(3)
  }
  finally {
    wrapper.unmount()
    disposePinia(pinia)
    vi.unstubAllGlobals()
  }
})
