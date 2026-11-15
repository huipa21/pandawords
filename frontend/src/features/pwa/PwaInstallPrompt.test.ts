import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { runInNewContext } from 'node:vm'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createAppI18n } from '@/i18n'
import PwaInstallPrompt from './PwaInstallPrompt.vue'

runInNewContext(readFileSync(resolve('public/pwa-install.v1.js'), 'utf8'), { window })

const wrappers: ReturnType<typeof mount>[] = []
function render(locale: 'en' | 'zh-CN' = 'en') {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(PwaInstallPrompt, {
    global: {
      plugins: [i18n],
    },
  })
  wrappers.push(wrapper)
  return wrapper
}
function available(outcome: 'accepted' | 'dismissed' = 'accepted', prompt = vi.fn(async () => {})) {
  const event = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
    prompt,
    userChoice: Promise.resolve({ outcome }),
  })
  window.dispatchEvent(event)
  return event
}
beforeEach(() => localStorage.clear())
afterEach(() => {
  for (const wrapper of wrappers.splice(0))
    wrapper.unmount()
  vi.restoreAllMocks()
})

it('preserves ordinary browsing without an install event and exposes localized labelled controls only when supported', async () => {
  const wrapper = render()
  expect(wrapper.find('section').exists()).toBe(false)
  const unsupported = new Event('beforeinstallprompt', { cancelable: true })
  window.dispatchEvent(unsupported)
  await flushPromises()
  expect(unsupported.defaultPrevented).toBe(true)
  expect(wrapper.find('section').exists()).toBe(false)
  const event = available()
  await flushPromises()
  expect(event.defaultPrevented).toBe(true)
  expect(wrapper.get('section').attributes('aria-labelledby')).toBe(wrapper.get('h2').attributes('id'))
  expect(wrapper.text()).toContain('Install PandaWords')
  expect(wrapper.findAll('button').map(button => button.text())).toEqual(['Install', 'Not now'])
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(event.prompt).toHaveBeenCalledOnce()
  expect(wrapper.find('section').exists()).toBe(false)
  available()
  await flushPromises()
  expect(wrapper.find('section').exists()).toBe(false)
})

it('retains a supported event received before the root component mounts', async () => {
  const event = available()
  const wrapper = render()
  await flushPromises()
  expect(event.defaultPrevented).toBe(true)
  expect(wrapper.text()).toContain('Install PandaWords')
  await wrapper.findAll('button')[1]!.trigger('click')
})

it('updates the visible prompt when the locale changes', async () => {
  const i18n = createAppI18n()
  i18n.global.locale.value = 'en'
  const wrapper = mount(PwaInstallPrompt, {
    global: {
      plugins: [i18n],
    },
  })
  wrappers.push(wrapper)
  available()
  await flushPromises()
  expect(wrapper.text()).toContain('Install PandaWords')
  i18n.global.locale.value = 'zh-CN'
  await flushPromises()
  expect(wrapper.text()).toContain('安装 PandaWords')
  await wrapper.findAll('button')[1]!.trigger('click')
})

it('dismisses the Chinese prompt persistently across remounts', async () => {
  const wrapper = render('zh-CN')
  available()
  await flushPromises()
  expect(wrapper.text()).toContain('安装 PandaWords')
  await wrapper.findAll('button')[1]!.trigger('click')
  expect(wrapper.find('section').exists()).toBe(false)
  wrapper.unmount()
  const next = render('zh-CN')
  available()
  await flushPromises()
  expect(next.find('section').exists()).toBe(false)
})

it.each(['dismissed', 'accepted'] as const)('does not reoffer after native choice %s', async (outcome) => {
  const wrapper = render()
  available(outcome)
  await flushPromises()
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  available()
  await flushPromises()
  expect(wrapper.find('section').exists()).toBe(false)
})

it.each([
  ['en', 'Installation couldn\'t start. You can continue using PandaWords in your browser.', 'Not now'],
  ['zh-CN', '无法启动安装。你仍可在浏览器中使用 PandaWords。', '暂不安装'],
] as const)('shows accessible %s feedback for native prompt failure and recovers on a new event', async (locale, message, dismiss) => {
  const wrapper = render(locale)
  available('dismissed', vi.fn(async () => {
    throw new Error('sensitive native prompt details')
  }))
  await flushPromises()
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe(message)
  expect(wrapper.text()).not.toContain('sensitive native prompt details')
  expect(wrapper.findAll('button').map(button => button.text())).toEqual([dismiss])
  expect(localStorage.getItem('pandawords.install-dismissed.v1')).toBeNull()

  const next = available()
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.findAll('button')).toHaveLength(2)
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(next.prompt).toHaveBeenCalledOnce()
  expect(wrapper.find('section').exists()).toBe(false)
})

it('shows feedback if the native user choice rejects', async () => {
  let rejectChoice!: (reason: Error) => void
  const userChoice = new Promise<{ outcome: 'accepted' | 'dismissed' }>((_, reject) => {
    rejectChoice = reject
  })
  const wrapper = render()
  const event = Object.assign(new Event('beforeinstallprompt', { cancelable: true }), {
    prompt: vi.fn(async () => rejectChoice(new Error('sensitive choice details'))),
    userChoice,
  })
  window.dispatchEvent(event)
  await flushPromises()
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe('Installation couldn\'t start. You can continue using PandaWords in your browser.')
  expect(wrapper.text()).not.toContain('sensitive choice details')
  expect(localStorage.getItem('pandawords.install-dismissed.v1')).toBeNull()
})

it('does not replace a newer install event with a stale prompt failure', async () => {
  let rejectPrompt!: (reason: Error) => void
  const wrapper = render()
  available('accepted', vi.fn(() => new Promise<void>((_, reject) => {
    rejectPrompt = reject
  })))
  await flushPromises()
  await wrapper.findAll('button')[0]!.trigger('click')
  const next = available()
  await flushPromises()
  rejectPrompt(new Error('old prompt failed'))
  await flushPromises()
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  expect(wrapper.findAll('button')).toHaveLength(2)
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(next.prompt).toHaveBeenCalledOnce()
})

it('does not persist a native prompt failure, even when storage is denied', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
    throw new Error('denied')
  })
  const save = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('denied')
  })
  const wrapper = render()
  available('dismissed', vi.fn(async () => {
    throw new Error('unavailable')
  }))
  await flushPromises()
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('Installation couldn\'t start.')
  expect(save).not.toHaveBeenCalled()
  available()
  await flushPromises()
  expect(wrapper.find('section').exists()).toBe(true)
  expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  await wrapper.findAll('button')[1]!.trigger('click')
})

it('does not offer installation in standalone mode', async () => {
  vi.spyOn(window, 'matchMedia').mockReturnValue({ matches: true } as MediaQueryList)
  const standalone = render()
  const event = available()
  await flushPromises()
  expect(event.defaultPrevented).toBe(true)
  expect(standalone.find('section').exists()).toBe(false)
})

it('stops offering installation when the app is installed elsewhere', async () => {
  let rejectPrompt!: (reason: Error) => void
  const wrapper = render()
  available('accepted', vi.fn(() => new Promise<void>((_, reject) => {
    rejectPrompt = reject
  })))
  await flushPromises()
  expect(wrapper.find('section').exists()).toBe(true)
  await wrapper.findAll('button')[0]!.trigger('click')
  window.dispatchEvent(new Event('appinstalled'))
  rejectPrompt(new Error('old prompt failed after installation'))
  await flushPromises()
  expect(wrapper.find('section').exists()).toBe(false)
  available()
  await flushPromises()
  expect(wrapper.find('section').exists()).toBe(false)
  expect(localStorage.getItem('pandawords.install-dismissed.v1')).toBe('1')
})
