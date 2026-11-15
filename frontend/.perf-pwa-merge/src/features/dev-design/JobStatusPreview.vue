<script setup lang="ts">
import type { components } from '@/api/schema'
import { useI18n } from 'vue-i18n'
import JobStatus from '@/components/app/JobStatus.vue'

const { t } = useI18n()
const jobs: components['schemas']['JobRead'][] = (['queued', 'running', 'done', 'failed'] as const).map(status => ({
  id: `job:preview-${status}`,
  type: 'enrich_dictionary',
  status,
  attempts: 1,
  run_after: '2026-11-14T00:00:00Z',
}))
</script>

<template>
  <section class="space-y-4">
    <h2 class="text-xl font-semibold">
      {{ t('jobs.preview') }}
    </h2>
    <JobStatus :jobs="jobs" :active="false" />
  </section>
</template>
