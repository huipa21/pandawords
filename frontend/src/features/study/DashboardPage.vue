<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '@/api/client'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import ExamSummary from './ExamSummary.vue'
import StudyCounts from './StudyCounts.vue'
import StudyForecast from './StudyForecast.vue'
import { useStudyResource } from './useStudyResource'

const { t, n } = useI18n()
const router = useRouter()
const { data, loading, error, load } = useStudyResource(() => 'dashboard', () => api.GET('/api/dashboard'))
</script>

<template>
  <section class="grid gap-6" data-testid="study-dashboard">
    <PageHeader :title="t('study.dashboard')">
      <template #actions>
        <NButton size="large" :loading="loading" @click="load">
          {{ t('study.refresh') }}
        </NButton>
      </template>
    </PageHeader>
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="6" />
    </div>
    <ErrorState v-else-if="error" :error="error" @retry="load" />
    <template v-else-if="data">
      <NCard>
        <StudyCounts :due="data.due_today" :fresh="data.new_today" :today="data.today" due-today available-today />
        <dl class="grid gap-4 sm:grid-cols-2">
          <div>
            <dt>{{ t('study.retention') }}</dt>
            <dd class="m-0 text-xl font-semibold">
              {{ data.retention_30_days === null ? t('study.noHistory') : n(data.retention_30_days, { style: 'percent', maximumFractionDigits: 1 }) }}
            </dd>
          </div>
          <div>
            <dt>{{ t('study.streak') }}</dt>
            <dd class="m-0 text-xl font-semibold">
              {{ t('study.streakDays', { count: data.streak }) }}
            </dd>
          </div>
        </dl>
        <p class="text-sm text-muted">
          {{ t('study.utcNotice') }}
        </p>
      </NCard>
      <NCard>
        <StudyForecast :days="data.forecast" />
      </NCard>
      <EmptyState v-if="!data.projects.length" title-key="study.empty" desc-key="study.emptyDescription">
        <template #action>
          <NButton size="large" @click="router.push({ name: 'projects' })">
            {{ t('pages.projects') }}
          </NButton>
        </template>
      </EmptyState>
      <NCard v-for="project in data.projects" :key="project.project_id" :title="project.name">
        <div class="grid gap-4">
          <StudyCounts :due="project.due" :fresh="project.new" :today="project.today" due-today />
          <ExamSummary :exam="project.exam" />
          <StudyForecast :days="project.forecast" />
          <div class="flex flex-wrap gap-3">
            <NButton size="large" type="primary" :aria-label="t('study.reviewProject', { name: project.name })" @click="router.push({ name: 'project-review', params: { id: project.project_id } })">
              {{ t('study.startReview') }}
            </NButton>
            <NButton size="large" :aria-label="t('study.planProject', { name: project.name })" @click="router.push({ name: 'project-plan', params: { id: project.project_id } })">
              {{ t('pages.plan') }}
            </NButton>
          </div>
        </div>
      </NCard>
    </template>
  </section>
</template>
