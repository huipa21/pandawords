<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import AddWordDialog from './AddWordDialog.vue'
import { useProject } from './useProject'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { project, loading, loadError, load } = useProject(() => String(route.params.id))
const adding = ref(false)
</script>

<template>
  <section class="grid gap-6" data-testid="project-detail">
    <PageHeader :title="project?.name ?? t('pages.project')">
      <template #actions>
        <NButton v-if="project" size="large" type="primary" data-testid="project-add-word" @click="adding = true">
          {{ t('addWord.title') }}
        </NButton>
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
      <EmptyState title-key="projects.treePending" desc-key="projects.treeNotice" />
      <AddWordDialog v-model:show="adding" :project-id="project.id" />
    </template>
  </section>
</template>
