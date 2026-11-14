import type { Reading } from './readingText'
import type { components } from '@/api/schema'
import { onScopeDispose, ref } from 'vue'
import { api } from '@/api/client'

export function useReading() {
  const reading = ref<Reading>()
  const passages = ref<components['schemas']['ContentRead'][]>([])
  const projects = ref<components['schemas']['ProjectRead'][]>([])
  const projectPage = ref(1)
  const moreProjects = ref(false)
  const loading = ref(false)
  const failed = ref(false)
  const unavailable = ref(false)
  const projectId = ref<string | null>(null)
  const passageId = ref('')
  const title = ref('')
  const source = ref('')
  const text = ref('')
  const offset = ref(0)
  const more = ref(false)
  let request = 0
  let readingScope = ''
  onScopeDispose(() => request++)

  async function load() {
    const current = ++request
    loading.value = true
    failed.value = false
    unavailable.value = false
    const scope = JSON.stringify([passageId.value, projectId.value])
    if (scope !== readingScope && reading.value)
      reading.value = { ...reading.value, project_senses: [] }
    readingScope = scope
    try {
      const result = await api.GET('/api/content/passage/{id}/reading', {
        params: {
          path: { id: passageId.value },
          query: { project_id: projectId.value ?? undefined },
        },
      })
      if (current !== request)
        return
      if (!result.data) {
        failed.value = true
        unavailable.value = result.response.status === 404
      }
      else {
        reading.value = result.data as Reading
      }
    }
    catch {
      if (current === request)
        failed.value = true
    }
    finally {
      if (current === request)
        loading.value = false
    }
  }

  async function list() {
    loading.value = true
    failed.value = false
    try {
      const [contents, choices] = await Promise.all([
        api.GET('/api/content/{kind}', {
          params: {
            path: { kind: 'passage' },
            query: { limit: 50, offset: offset.value },
          },
        }),
        api.GET('/api/projects', {
          params: {
            query: { page: 1, page_size: 100 },
          },
        }),
      ])
      if (!contents.data || !choices.data)
        throw new Error('unavailable')
      passages.value = contents.data
      more.value = contents.data.length === 50
      projects.value = choices.data.items
      projectPage.value = 1
      moreProjects.value = choices.data.total > 100
      return true
    }
    catch {
      failed.value = true
      return false
    }
    finally {
      loading.value = false
    }
  }

  async function loadMoreProjects() {
    loading.value = true
    failed.value = false
    try {
      const result = await api.GET('/api/projects', {
        params: {
          query: { page: projectPage.value + 1, page_size: 100 },
        },
      })
      if (!result.data)
        throw new Error('unavailable')
      projects.value.push(...result.data.items)
      projectPage.value++
      moreProjects.value = projectPage.value * 100 < result.data.total
    }
    catch {
      failed.value = true
    }
    finally {
      loading.value = false
    }
  }

  async function ingest() {
    if (!text.value.trim() || loading.value)
      return
    loading.value = true
    failed.value = false
    try {
      const result = await api.POST('/api/content/ingest', {
        body: {
          text: text.value,
          title: title.value,
          source: source.value,
          lang: 'en',
        },
      })
      if (!result.data)
        throw new Error('unavailable')
      passageId.value = result.data.passage.id
      return passageId.value
    }
    catch {
      failed.value = true
    }
    finally {
      loading.value = false
    }
  }
  return {
    reading,
    passages,
    projects,
    moreProjects,
    loadMoreProjects,
    loading,
    failed,
    unavailable,
    projectId,
    passageId,
    title,
    source,
    text,
    offset,
    more,
    load,
    list,
    ingest,
  }
}
