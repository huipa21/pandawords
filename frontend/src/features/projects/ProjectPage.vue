<script setup lang="ts">
import type { Component } from 'vue'
import { ref, shallowRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import ProjectExportButton from '@/features/portability/ProjectExportButton.vue'
import AddWordDialog from './AddWordDialog.vue'
import { loadProjectGraph } from './graphLoader'
import ProjectTree from './ProjectTree.vue'
import { useProject } from './useProject'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { project, loading, loadError, load } = useProject(() => String(route.params.id))
const adding = ref(false)
const tree = ref<InstanceType<typeof ProjectTree>>()
const view = ref<'tree' | 'graph'>('tree')
const graphFocus = ref('')
const graphComponent = shallowRef<Component>()
const graphLoading = ref(false)
const graphError = ref(false)

async function showGraph() {
  view.value = 'graph'
  if (graphComponent.value || graphLoading.value)
    return
  graphLoading.value = true
  graphError.value = false
  try {
    graphComponent.value = (await loadProjectGraph()).default
  }
  catch {
    graphError.value = true
  }
  finally {
    graphLoading.value = false
  }
}

watch(() => route.params.id, () => {
  graphFocus.value = ''
  view.value = 'tree'
})
</script>

<template>
  <section class="grid gap-6" data-testid="project-detail">
    <PageHeader :title="project?.name ?? t('pages.project')">
      <template #actions>
        <NButton v-if="project" size="large" @click="router.push({ name: 'project-plan', params: { id: project.id } })">
          {{ t('pages.plan') }}
        </NButton>
        <NButton v-if="project" size="large" @click="router.push({ name: 'project-review', params: { id: project.id } })">
          {{ t('study.startReview') }}
        </NButton>
        <NButton v-if="project" size="large" type="primary" data-testid="project-add-word" @click="adding = true">
          {{ t('addWord.title') }}
        </NButton>
        <ProjectExportButton v-if="project" :project-id="project.id" />
        <NButton size="large" @click="router.push({ name: 'projects' })">
          {{ t('pages.projects') }}
        </NButton>
        <NButton v-if="project" size="large" type="primary" data-testid="project-edit" @click="router.push({ name: 'project-edit', params: { id: project.id } })">
          {{ t('projects.edit') }}
        </NButton>
      </template>
    </PageHeader>
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="4" />
    </div>
    <ErrorState v-else-if="loadError" :error="loadError" @retry="load" />
    <template v-else-if="project">
      <NCard>
        <p v-if="project.description" class="whitespace-pre-wrap break-words">
          {{ project.description }}
        </p>
        <p class="break-words text-muted">
          {{ t('projects.languages', { target: project.target_lang, source: project.source_lang }) }}
        </p>
        <p>{{ t('projects.dailyNew', { count: project.plan.daily_new ?? 20 }) }}</p>
      </NCard>
      <div class="flex gap-2" role="group" :aria-label="t('graph.view')">
        <NButton size="large" :aria-pressed="view === 'tree'" @click="view = 'tree'">
          {{ t('graph.tree') }}
        </NButton>
        <NButton size="large" :aria-pressed="view === 'graph'" @click="showGraph">
          {{ t('graph.title') }}
        </NButton>
      </div>
      <ProjectTree v-show="view === 'tree'" :key="project.id" ref="tree" :project-id="project.id" :source-lang="project.source_lang" @add="adding = true" />
      <div v-if="view === 'graph' && graphLoading" role="status" :aria-label="t('common.loading')">
        <NSkeleton text :repeat="4" />
      </div>
      <ErrorState v-else-if="view === 'graph' && graphError" :error="t('graph.error')" @retry="showGraph" />
      <component :is="graphComponent" v-else-if="view === 'graph' && graphComponent" :key="project.id" :project-id="project.id" :initial-focus="graphFocus" @focus="graphFocus = $event" />
      <AddWordDialog v-model:show="adding" :project-id="project.id" @added="tree?.refresh()" @jobs-settled="tree?.refresh()" />
    </template>
  </section>
</template>
