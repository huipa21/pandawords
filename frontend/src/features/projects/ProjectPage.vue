<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import AddWordDialog from './AddWordDialog.vue'
import ProjectTree from './ProjectTree.vue'
import { useProject } from './useProject'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { project, loading, loadError, load } = useProject(() => String(route.params.id))
const adding = ref(false)
const tree = ref<InstanceType<typeof ProjectTree>>()
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
      <ProjectTree :key="project.id" ref="tree" :project-id="project.id" :source-lang="project.source_lang" @add="adding = true" />
      <AddWordDialog v-model:show="adding" :project-id="project.id" @added="tree?.refresh()" @jobs-settled="tree?.refresh()" />
    </template>
  </section>
</template>
