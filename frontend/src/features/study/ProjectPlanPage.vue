<script setup lang="ts">
import type { ProjectCreate } from '@/features/projects/useProject'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { api } from '@/api/client'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import ProjectForm from '@/features/projects/ProjectForm.vue'
import { useProject } from '@/features/projects/useProject'
import ExamSummary from './ExamSummary.vue'
import RetentionSettings from './RetentionSettings.vue'
import SenseOrderEditor from './SenseOrderEditor.vue'
import StudyCounts from './StudyCounts.vue'
import StudyForecast from './StudyForecast.vue'
import { useStudyResource } from './useStudyResource'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const id = computed(() => String(route.params.id))
const { project, loading, busy, loadError, fields, load, save } = useProject(() => id.value)
const plan = useStudyResource(() => id.value, id => api.GET('/api/projects/{id}/study-plan', {
  params: {
    path: { id },
    query: { limit: 1 },
  },
}))
const saved = ref(false)
async function submit(body: ProjectCreate) {
  saved.value = false
  const result = await save(body)
  if (result) {
    project.value = result
    saved.value = true
    await plan.load()
  }
}
</script>

<template>
  <section class="grid gap-6" data-testid="project-plan">
    <PageHeader :title="t('study.projectTitle', { name: project?.name ?? t('pages.project') })">
      <template #actions>
        <NButton size="large" @click="router.push({ name: 'project', params: { id } })">
          {{ t('pages.project') }}
        </NButton>
        <NButton size="large" @click="router.push({ name: 'review' })">
          {{ t('study.dashboard') }}
        </NButton>
      </template>
    </PageHeader>
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="6" />
    </div>
    <ErrorState v-else-if="loadError" :error="loadError" @retry="load" />
    <template v-else-if="project">
      <NCard :title="t('study.summary')">
        <div v-if="plan.loading.value" role="status" :aria-label="t('common.loading')">
          <NSkeleton text :repeat="4" />
        </div>
        <ErrorState v-else-if="plan.error.value" :error="plan.error.value" @retry="plan.load" />
        <div v-else-if="plan.data.value" class="grid gap-4">
          <StudyCounts :due="plan.data.value.due" :fresh="plan.data.value.new" :today="plan.data.value.today" />
          <p>{{ t('study.allowances', { fresh: plan.data.value.remaining_new_allowance, reviews: plan.data.value.remaining_review_allowance ?? t('projects.unlimited') }) }}</p>
          <NAlert v-if="plan.data.value.plan.daily_new === 0 || plan.data.value.plan.review_cap === 0" type="info">
            {{ t('study.zeroLimit') }}
          </NAlert>
          <ExamSummary :exam="plan.data.value.exam" />
          <StudyForecast :days="plan.data.value.forecast" />
          <p class="text-sm text-muted">
            {{ t('study.utcNotice') }}
          </p>
          <EmptyState v-if="!plan.data.value.queue_total" title-key="study.queueEmpty" desc-key="study.queueEmptyDescription" />
          <NButton size="large" type="primary" :disabled="!plan.data.value.queue_total" @click="router.push({ name: 'project-review', params: { id } })">
            {{ t('study.startReview') }}
          </NButton>
        </div>
      </NCard>
      <NCard :title="t('study.projectSettings')">
        <p v-if="saved" role="status" class="mb-4">
          {{ t('study.saved') }}
        </p>
        <ProjectForm :key="project.id" :initial="project" :busy="busy" :fields="fields" :save="submit" @cancel="router.push({ name: 'project', params: { id } })" />
      </NCard>
      <SenseOrderEditor :key="id" :project-id="id" @saved="plan.load" />
      <RetentionSettings :key="id" />
    </template>
  </section>
</template>
