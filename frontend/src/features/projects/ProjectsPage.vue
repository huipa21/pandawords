<script setup lang="ts">
import type { Project } from './useProject'
import { useMessage } from 'naive-ui'
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import { useProjectErrors } from './useProject'

const { t } = useI18n()
const router = useRouter()
const message = useMessage()
const errorText = useProjectErrors()
const items = ref<Project[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const loaded = ref(false)
const error = ref('')
const pending = ref<Project>()
const deleting = ref(false)
const pages = computed(() => Math.max(1, Math.ceil(total.value / 20)))
let requested = 1
let request = 0
let disposed = false

async function load(target = page.value) {
  const current = ++request
  requested = target
  loading.value = true
  error.value = ''
  try {
    const result = await api.GET('/api/projects', {
      params: {
        query: { page: target, page_size: 20 },
      },
    })
    if (current !== request || disposed)
      return
    if (result.data) {
      items.value = result.data.items
      page.value = result.data.page
      total.value = result.data.total
      loaded.value = true
    }
    else {
      error.value = errorText(result.error, result.response.status)
    }
  }
  catch {
    if (current === request && !disposed)
      error.value = t('errors.transport')
  }
  finally {
    if (current === request && !disposed)
      loading.value = false
  }
}

async function remove() {
  if (!pending.value || deleting.value)
    return
  deleting.value = true
  try {
    const result = await api.DELETE('/api/projects/{id}', {
      params: {
        path: { id: pending.value.id },
      },
    })
    if (disposed)
      return
    if (!result.response.ok) {
      message.error(errorText(result.error, result.response.status))
      return
    }
    const deleted = pending.value.id
    items.value = items.value.filter(item => item.id !== deleted)
    total.value = Math.max(0, total.value - 1)
    page.value = Math.min(page.value, pages.value)
    pending.value = undefined
    message.success(t('projects.deleted'), { duration: 2000 })
    await load()
  }
  catch {
    if (!disposed)
      message.error(t('errors.transport'))
  }
  finally {
    deleting.value = false
  }
}

onMounted(() => load())
onScopeDispose(() => {
  disposed = true
  request++
})
</script>

<template>
  <section class="grid gap-6" data-testid="projects-page">
    <PageHeader :title="t('pages.projects')">
      <template #actions>
        <NSpin v-if="loaded && loading" size="small" :aria-label="t('common.loading')" />
        <NButton size="large" :disabled="loading || deleting" @click="load()">
          {{ t('common.refresh') }}
        </NButton>
        <NButton size="large" type="primary" data-testid="project-create" @click="router.push({ name: 'project-create' })">
          {{ t('projects.create') }}
        </NButton>
      </template>
    </PageHeader>
    <div v-if="loading && !loaded" role="status" :aria-label="t('common.loading')" class="grid gap-4">
      <NSkeleton v-for="index in 3" :key="index" text :repeat="3" />
    </div>
    <ErrorState v-if="error" :error="error" :loading="loading" @retry="load(requested)" />
    <EmptyState v-if="loaded && !items.length && !error" title-key="projects.empty" desc-key="projects.emptyHint">
      <template #action>
        <NButton size="large" @click="router.push({ name: 'project-create' })">
          {{ t('projects.create') }}
        </NButton>
      </template>
    </EmptyState>
    <div v-if="items.length" class="grid gap-4 lg:grid-cols-2" data-testid="project-list">
      <NCard v-for="item in items" :key="item.id" data-testid="project-card">
        <RouterLink :to="{ name: 'project', params: { id: item.id } }" class="project-link inline-flex items-center break-all text-lg text-primary font-semibold focus-visible:pw-focus-ring">
          {{ item.name }}
        </RouterLink>
        <p v-if="item.description" class="whitespace-pre-wrap break-words">
          {{ item.description }}
        </p>
        <p class="break-words text-muted">
          {{ t('projects.languages', { target: item.target_lang, source: item.source_lang }) }}
        </p>
        <div class="flex flex-wrap gap-3">
          <NButton size="large" :disabled="deleting" data-testid="project-edit" @click="router.push({ name: 'project-edit', params: { id: item.id } })">
            {{ t('projects.edit') }}
          </NButton>
          <NButton size="large" type="error" secondary :disabled="deleting || loading" data-testid="project-delete" @click="pending = item">
            {{ t('projects.delete') }}
          </NButton>
        </div>
      </NCard>
    </div>
    <nav v-if="loaded && total > 0" class="flex flex-wrap items-center justify-between gap-3" :aria-label="t('projects.pagination')">
      <NButton size="large" :disabled="page <= 1 || loading || deleting" @click="load(page - 1)">
        {{ t('common.previous') }}
      </NButton>
      <span>{{ t('projects.page', { page, pages, total }) }}</span>
      <NButton size="large" :disabled="page >= pages || loading || deleting" @click="load(page + 1)">
        {{ t('common.next') }}
      </NButton>
    </nav>
    <ConfirmAction
      :show="!!pending" title-key="projects.delete" content-key="projects.deleteNotice"
      :params="{ name: pending?.name ?? '' }" :loading="deleting"
      @confirm="remove" @cancel="pending = undefined"
    />
  </section>
</template>

<style scoped>
.project-link {
  min-height: var(--pw-layout-touch-target);
}
</style>
