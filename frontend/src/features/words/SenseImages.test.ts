import type { components } from '@/api/schema'
import { flushPromises, mount } from '@vue/test-utils'
import { NConfigProvider } from 'naive-ui'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { createAppI18n } from '@/i18n'
import ProtectedImage from './ProtectedImage.vue'
import SenseImages from './SenseImages.vue'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
const image: components['schemas']['MediaRead'] = {
  id: 'media:opaque',
  target: 'sense:opaque',
  kind: 'image',
  mime: 'image/png',
  source: 'upload',
  attribution: null,
  accent: null,
}
let items: components['schemas']['MediaRead'][]
let cleanup: (() => void) | undefined
function ok(data: unknown) {
  return {
    data,
    response: new Response(null, { status: 200 }),
  }
}
async function setup(locale: 'en' | 'zh-CN' = 'en') {
  const i18n = createAppI18n()
  i18n.global.locale.value = locale
  const wrapper = mount(defineComponent({
    setup: () => () => h(NConfigProvider, null, {
      default: () => h(SenseImages, { senseId: 'sense:opaque' }),
    }),
  }), {
    global: {
      plugins: [i18n],
    },
    attachTo: document.body,
  })
  cleanup = () => wrapper.unmount()
  await flushPromises()
  return wrapper
}
beforeEach(() => {
  vi.resetAllMocks()
  items = []
  vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:private-image')
  vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
  client.GET.mockImplementation(async (path: string) => {
    if (path === '/api/media/{rid}')
      return ok(new Blob(['image'], { type: 'image/png' }))
    if (path === '/api/jobs/{id}')
      return ok({ id: 'job', status: 'done' })
    if (path.endsWith('/search')) {
      return ok({
        search_id: 'a'.repeat(64),
        results: [
          {
            id: 123,
            creator: 'Creator',
            source_page: 'https://pixabay.com/photos/123/',
            attribution: 'Pixabay Content License',
          },
        ],
      })
    }
    return ok([...items])
  })
  client.POST.mockImplementation(async (path: string) => {
    items = [image]
    return path.endsWith('/pixabay')
      ? ok({ id: 'job', status: 'queued' })
      : ok(image)
  })
  client.DELETE.mockImplementation(async () => {
    items = []
    return {
      response: new Response(null, { status: 204 }),
    }
  })
})
afterEach(() => {
  cleanup?.()
  cleanup = undefined
  vi.restoreAllMocks()
  document.body.innerHTML = ''
})

describe('sense images', () => {
  it('uploads without a provider, displays authenticated blobs and confirms removal', async () => {
    const wrapper = await setup()
    expect(wrapper.text()).toContain('No private images attached')
    const input = wrapper.get('input[type="file"]')
    expect(input.element.closest('label')?.textContent).toContain('Upload an image')
    const file = new File(['image'], 'private.png', { type: 'image/png' })
    Object.defineProperty(input.element, 'files', {
      value: [file],
      configurable: true,
    })
    await input.trigger('change')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/images/senses/{sense_id}', expect.objectContaining({
      headers: { 'Content-Type': 'image/png' },
      bodySerializer: expect.any(Function),
    }))
    expect(wrapper.get('img').attributes('src')).toBe('blob:private-image')
    expect(wrapper.get('img').attributes('alt')).toBe('Private vocabulary image')
    expect(client.GET).toHaveBeenCalledWith('/api/media/{rid}', expect.objectContaining({ parseAs: 'blob' }))
    await wrapper.findAll('button').find(button => button.text() === 'Remove image')!.trigger('click')
    expect(client.DELETE).not.toHaveBeenCalled()
    wrapper.findComponent(ConfirmAction).vm.$emit('confirm')
    await flushPromises()
    expect(client.DELETE).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:private-image')
    expect(wrapper.find('img').exists()).toBe(false)
  })

  it('searches explicitly, selects a server identity and waits for the worker', async () => {
    const wrapper = await setup()
    expect(client.GET.mock.calls.some(([path]) => String(path).endsWith('/search'))).toBe(false)
    await wrapper.get('input:not([type="file"])').setValue('apple')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('a').attributes('href')).toBe('https://pixabay.com/photos/123/')
    expect(wrapper.text()).toContain('Pixabay #123 by Creator')
    await wrapper.findAll('button').find(button => button.text() === 'Download and attach')!.trigger('click')
    await flushPromises()
    expect(client.POST).toHaveBeenCalledWith('/api/images/senses/{sense_id}/pixabay', expect.objectContaining({
      body: {
        request_id: expect.any(String),
        search_id: 'a'.repeat(64),
        result_id: 123,
      },
    }))
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('keeps the file and request identity after failure for a safe retry', async () => {
    client.POST.mockResolvedValueOnce({
      error: { code: 'image.disabled' },
      response: new Response(null, { status: 503 }),
    })
    const wrapper = await setup()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      value: [
        new File(['x'], 'image.png', { type: 'image/png' }),
      ],
    })
    await input.trigger('change')
    await flushPromises()
    expect(wrapper.text()).toContain('Image operation failed')
    const firstIdentity = client.POST.mock.calls[0]![1].params.header['request-id']
    await wrapper.findAll('button').find(button => button.text() === 'Retry')!.trigger('click')
    await flushPromises()
    expect(client.POST.mock.calls[1]![1].params.header['request-id']).toBe(firstIdentity)
    expect(wrapper.find('img').exists()).toBe(true)
  })

  it('localizes accessible controls', async () => {
    const wrapper = await setup('zh-CN')
    expect(wrapper.get('section').attributes('aria-label')).toBe('私人义项图片')
    expect(wrapper.text()).toContain('上传图片')
    expect(wrapper.text()).toContain('搜索 Pixabay')
    expect(wrapper.text()).not.toContain('images.')
  })

  it('revokes blobs on replacement/unmount and ignores late protected responses', async () => {
    const i18n = createAppI18n()
    const wrapper = mount(ProtectedImage, {
      props: { mediaId: 'media:first' },
      global: {
        plugins: [i18n],
      },
    })
    cleanup = () => wrapper.unmount()
    await flushPromises()
    await wrapper.setProps({ mediaId: 'media:second' })
    await flushPromises()
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1)
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise(done => resolve = done))
    await wrapper.setProps({ mediaId: 'media:late' })
    const created = vi.mocked(URL.createObjectURL).mock.calls.length
    wrapper.unmount()
    cleanup = undefined
    resolve(ok(new Blob(['late'])))
    await flushPromises()
    expect(URL.createObjectURL).toHaveBeenCalledTimes(created)
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
  })
})
