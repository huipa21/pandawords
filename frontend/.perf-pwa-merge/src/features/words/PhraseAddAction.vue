<script setup lang="ts">
import type { components } from '@/api/schema'
import { onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import AddWordDialog from '@/features/projects/AddWordDialog.vue'

defineProps<{ text: string }>()
const { t } = useI18n()
const choosing = ref(false)
const loading = ref(false)
const error = ref('')
const projects = ref<components['schemas']['ProjectRead'][]>([])
const projectId = ref<string>()
const adding = ref(false)
const page = ref(1)
const hasMore = ref(false)
let generation = 0

async function load(reset = true) {
  const current = ++generation
  choosing.value = true
  loading.value = true
  error.value = ''
  if (reset) {
    page.value = 1
    projects.value = []
    projectId.value = undefined
  }
  try {
    const result = await api.GET('/api/projects', {
      params: {
        query: { page: page.value, page_size: 100 },
      },
    })
    if (current !== generation)
      return
    if (!result.data)
      throw new Error()
    projects.value.push(...result.data.items)
    hasMore.value = page.value * 100 < result.data.total
    page.value++
  }
  catch {
    if (current === generation)
      error.value = t('phrases.projectError')
  }
  finally {
    if (current === generation)
      loading.value = false
  }
}
onScopeDispose(() => generation++)
</script>

<template>
  <div class="space-y-3">
    <NButton size="large" data-testid="phrase-add" @click="load()">
      {{ t('phrases.add') }}
    </NButton>
    <div v-if="choosing" class="space-y-3">
      <p v-if="loading" role="status">
        {{ t('common.loading') }}
      </p>
      <p v-if="error" role="alert">
        {{ error }}
      </p>
      <NButton v-if="error" size="large" @click="load(false)">
        {{ t('phrases.retry') }}
      </NButton>
      <p v-if="!loading && !error && !projects.length" role="status">
        {{ t('phrases.noProjects') }}
      </p>
      <label class="block">
        {{ t('phrases.project') }}
        <NSelect
          v-model:value="projectId" :disabled="loading"
          :options="projects.map(project => ({ label: project.name, value: project.id }))"
          :aria-label="t('phrases.project')" data-testid="phrase-project"
        />
      </label>
      <NButton v-if="hasMore" size="large" :disabled="loading" @click="load(false)">
        {{ t('phrases.more') }}
      </NButton>
      <NButton size="large" :disabled="!projectId || loading" data-testid="phrase-choose-senses" @click="adding = true">
        {{ t('word.selectSenses') }}
      </NButton>
    </div>
    <AddWordDialog v-if="projectId" v-model:show="adding" :project-id="projectId" :initial-text="text" />
  </div>
</template>
