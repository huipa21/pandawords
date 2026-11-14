import type { components } from '@/api/schema'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AddWordDialog from './AddWordDialog.vue'
import { button, failure, project, setup, success } from './testHarness'

const client = vi.hoisted(() => ({
  GET: vi.fn(),
  POST: vi.fn(),
  PATCH: vi.fn(),
  DELETE: vi.fn(),
}))
vi.mock('@/api/client', () => ({ api: client }))
vi.mock('@/components/graph/GraphCanvas.vue', () => ({
  default: { name: 'GraphCanvas', template: '<div />' },
}))
type Branch = components['schemas']['ProjectTreeLemmaRead']
let cleanup: (() => void) | undefined
let branches: Branch[]
const record = (id: string, table: components['schemas']['DictionaryTable'], fields: Record<string, unknown>) => ({ id, table, owner: null, fields })

function branch(): Branch {
  return {
    lemma: record('lemma:run/a', 'lemma', { text: 'run', kind: 'word' }),
    hidden: false,
    effective_hidden: false,
    lexemes: [
      {
        lexeme: record('lexeme:run', 'lexeme', { pos: 'verb' }),
        hidden: false,
        effective_hidden: false,
        senses: [
          {
            sense: record('sense:move', 'sense', {
              definition: 'move quickly',
              gloss: { zh: '跑' },
            }),
            hidden: false,
            effective_hidden: false,
          },
          {
            sense: record('sense:manage', 'sense', { definition: 'manage a business' }),
            hidden: true,
            effective_hidden: true,
          },
        ],
      },
    ],
  }
}
function treeResponse(page = 1, total = 1) {
  return success({
    items: structuredClone(branches),
    page,
    total,
    page_size: 20,
  })
}
function action(table: string, id: string) {
  const parent = document.querySelector(`[data-tree-table="${table}"][data-tree-id="${id}"]`)
  const element = parent?.querySelector<HTMLButtonElement>('[data-testid="project-tree-visibility"]')
  if (!element)
    throw new Error(`Missing action for ${table} ${id}`)
  element.click()
}
beforeEach(() => {
  vi.resetAllMocks()
  branches = [
    branch(),
  ]
  client.GET.mockImplementation((path: string) => Promise.resolve(path === '/api/projects/{id}'
    ? success(project)
    : treeResponse()))
  client.PATCH.mockImplementation((_path, options) => {
    const { table, target_id: id } = options.params.path
    const root = branches[0]!
    const lexeme = root.lexemes[0]!
    const node = table === 'lemma'
      ? root
      : table === 'lexeme'
        ? lexeme
        : lexeme.senses.find(item => item.sense.id === id)!
    node.hidden = options.body.hidden
    root.effective_hidden = root.hidden
    lexeme.effective_hidden = root.hidden || lexeme.hidden
    for (const sense of lexeme.senses)
      sense.effective_hidden = lexeme.effective_hidden || sense.hidden
    return Promise.resolve(success({
      id: 'item:1',
      target_id: id,
      hidden: node.hidden,
      added_at: project.created_at,
    }))
  })
})
afterEach(() => {
  cleanup?.()
  document.body.innerHTML = ''
})

describe('project tree', () => {
  it('switches to an on-demand graph and back without discarding the project tree', async () => {
    const app = await setup(`/projects/${project.id}`)
    cleanup = app.cleanup
    const tree = app.wrapper.findComponent({ name: 'ProjectTree' })
    const element = tree.element
    expect(client.GET.mock.calls.some(call => call[0] === '/api/graph')).toBe(false)
    await button('Graph').trigger('click')
    await flushPromises()
    expect(app.wrapper.find('[data-testid="graph-explorer"]').exists()).toBe(true)
    expect(app.wrapper.findComponent({ name: 'ProjectTree' }).element).toBe(element)
    await button('Tree').trigger('click')
    await flushPromises()
    expect(app.wrapper.findComponent({ name: 'ProjectTree' }).element).toBe(element)
    expect(app.wrapper.find('[data-testid="graph-explorer"]').exists()).toBe(false)
  })
  it('renders effective fields and accessible hidden management, preserving descendant flags', async () => {
    const app = await setup(`/projects/${project.id}`)
    cleanup = app.cleanup
    expect(client.GET).toHaveBeenCalledWith('/api/projects/{project_id}/tree', {
      params: {
        path: { project_id: project.id },
        query: { page: 1, page_size: 20, include_hidden: true },
      },
    })
    expect(app.wrapper.text()).toContain('move quickly')
    expect(app.wrapper.text()).toContain('跑')
    expect(app.wrapper.text()).not.toContain('manage a business')
    expect(app.wrapper.get('[data-testid="project-tree-word-link"]').attributes('href')).toBe('/words/lemma%3Arun%2Fa')
    action('lemma', 'lemma:run/a')
    await flushPromises()
    expect(app.wrapper.text()).not.toContain('move quickly')
    expect(app.wrapper.text()).toContain('No visible words on this page.')
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    expect(app.wrapper.text()).toContain('Hidden directly')
    expect(app.wrapper.text()).toContain('Hidden by an ancestor')
    expect(app.wrapper.text()).toContain('manage a business')
    action('lemma', 'lemma:run/a')
    await flushPromises()
    expect(branches[0]!.lexemes[0]!.senses[1]!.hidden).toBe(true)
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    expect(app.wrapper.text()).toContain('move quickly')
    expect(app.wrapper.text()).not.toContain('manage a business')
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    action('sense', 'sense:manage')
    await flushPromises()
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    expect(app.wrapper.text()).toContain('manage a business')
  })

  it('undoes a hide, including after paging, without deleting content', async () => {
    client.GET.mockImplementation((path: string) => Promise.resolve(path === '/api/projects/{id}'
      ? success(project)
      : treeResponse(1, 21)))
    const app = await setup(`/projects/${project.id}`)
    cleanup = app.cleanup
    action('sense', 'sense:move')
    await flushPromises()
    expect(app.wrapper.text()).not.toContain('move quickly')
    expect(client.PATCH).toHaveBeenLastCalledWith('/api/projects/{project_id}/tree/{table}/{target_id}/visibility', {
      params: {
        path: { project_id: project.id, table: 'sense', target_id: 'sense:move' },
      },
      body: { hidden: true },
    })
    client.GET.mockResolvedValueOnce(success({
      items: [],
      total: 21,
      page: 2,
      page_size: 20,
    }))
    await app.wrapper.get('[data-testid="project-tree-next"]').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('Page 2 of 2')
    client.GET.mockResolvedValueOnce(treeResponse(2, 21))
    await button('Undo').trigger('click')
    await flushPromises()
    expect(client.PATCH).toHaveBeenLastCalledWith('/api/projects/{project_id}/tree/{table}/{target_id}/visibility', {
      params: {
        path: { project_id: project.id, table: 'sense', target_id: 'sense:move' },
      },
      body: { hidden: false },
    })
    expect(app.wrapper.find('[data-testid="project-tree-undo"]').exists()).toBe(false)
    expect(client.DELETE).not.toHaveBeenCalled()
  })

  it('changes a directly hidden descendant without falsely restoring a hidden ancestor', async () => {
    branches[0]!.hidden = true
    branches[0]!.effective_hidden = true
    branches[0]!.lexemes[0]!.hidden = true
    branches[0]!.lexemes[0]!.effective_hidden = true
    branches[0]!.lexemes[0]!.senses.forEach(sense => sense.effective_hidden = true)
    const app = await setup(`/projects/${project.id}`)
    cleanup = app.cleanup
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    action('lexeme', 'lexeme:run')
    await flushPromises()
    expect(branches[0]!.lexemes[0]!.hidden).toBe(false)
    expect(branches[0]!.lexemes[0]!.effective_hidden).toBe(true)
    expect(app.wrapper.text()).toContain('Hidden by an ancestor')
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    expect(app.wrapper.text()).not.toContain('move quickly')
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    action('lemma', 'lemma:run/a')
    await flushPromises()
    await app.wrapper.get('[data-testid="project-tree-show-hidden"]').trigger('click')
    expect(app.wrapper.text()).toContain('move quickly')
    expect(app.wrapper.text()).not.toContain('manage a business')
  })

  it('retains the confirmed page on failure, retries it, and reports visibility errors', async () => {
    client.GET.mockImplementation((path: string) => Promise.resolve(path === '/api/projects/{id}'
      ? success(project)
      : treeResponse(1, 21)))
    const app = await setup(`/projects/${project.id}`, 'zh-CN')
    cleanup = app.cleanup
    client.GET.mockRejectedValueOnce(new Error('offline'))
    await app.wrapper.get('[data-testid="project-tree-next"]').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('无法连接服务器')
    expect(app.wrapper.text()).toContain('move quickly')
    client.GET.mockResolvedValueOnce(treeResponse(2, 21))
    await button('重试').trigger('click')
    await flushPromises()
    expect(client.GET).toHaveBeenLastCalledWith('/api/projects/{project_id}/tree', {
      params: {
        path: { project_id: project.id },
        query: { page: 2, page_size: 20, include_hidden: true },
      },
    })
    expect(app.wrapper.text()).toContain('第 2 / 2 页')
    client.PATCH.mockResolvedValueOnce(failure('auth.forbidden'))
    action('lexeme', 'lexeme:run')
    await flushPromises()
    expect(app.wrapper.get('[data-testid="project-tree-action-error"]').text()).toContain('你没有执行此操作的权限')
    expect(app.wrapper.text()).toContain('move quickly')
  })

  it('shows loading and empty/error states, and refreshes only the tree after add and settled jobs', async () => {
    let resolve!: (value: unknown) => void
    client.GET.mockImplementation((path: string) => path === '/api/projects/{id}'
      ? Promise.resolve(success(project))
      : new Promise(done => resolve = done))
    const app = await setup(`/projects/${project.id}`)
    cleanup = app.cleanup
    expect(app.wrapper.get('[data-testid="project-tree"] [role="status"]').attributes('aria-label')).toBe('Loading')
    resolve(failure('auth.forbidden'))
    await flushPromises()
    expect(app.wrapper.text()).toContain('You do not have permission')
    client.GET.mockResolvedValue(success({
      items: [],
      page: 1,
      total: 0,
      page_size: 20,
    }))
    await button('Retry').trigger('click')
    await flushPromises()
    expect(app.wrapper.text()).toContain('No words in this project yet.')
    client.GET.mockResolvedValue(treeResponse())
    const dialog = app.wrapper.findComponent(AddWordDialog)
    dialog.vm.$emit('added', {
      project_id: project.id,
      lemma_id: '',
      lexeme_ids: [],
      selected_sense_ids: [],
      membership_ids: [],
      jobs: [],
    })
    await flushPromises()
    expect(app.wrapper.text()).toContain('move quickly')
    dialog.vm.$emit('jobsSettled', [])
    await flushPromises()
    expect(client.GET.mock.calls.filter(([path]) => path === '/api/projects/{id}')).toHaveLength(1)
    expect(client.GET.mock.calls.filter(([path]) => path === '/api/projects/{project_id}/tree')).toHaveLength(4)
  })

  it('ignores a stale add refresh after a newer jobs-settled refresh', async () => {
    const app = await setup(`/projects/${project.id}`)
    cleanup = app.cleanup
    let resolve!: (value: unknown) => void
    client.GET.mockReturnValueOnce(new Promise(done => resolve = done))
    branches[0]!.lemma.fields.text = 'new result'
    client.GET.mockResolvedValueOnce(treeResponse())
    const dialog = app.wrapper.findComponent(AddWordDialog)
    dialog.vm.$emit('added', {
      project_id: project.id,
      lemma_id: '',
      lexeme_ids: [],
      selected_sense_ids: [],
      membership_ids: [],
      jobs: [],
    })
    dialog.vm.$emit('jobsSettled', [])
    await flushPromises()
    expect(app.wrapper.text()).toContain('new result')
    const stale = branch()
    stale.lemma.fields.text = 'stale result'
    resolve(success({
      items: [stale],
      page: 1,
      total: 1,
      page_size: 20,
    }))
    await flushPromises()
    expect(app.wrapper.text()).toContain('new result')
    expect(app.wrapper.text()).not.toContain('stale result')
  })
})
