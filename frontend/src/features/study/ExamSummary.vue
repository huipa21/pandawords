<script setup lang="ts">
import type { components } from '@/api/schema'
import { useI18n } from 'vue-i18n'

defineProps<{ exam: components['schemas']['ExamPacing'] | null }>()
const { t } = useI18n()
</script>

<template>
  <div v-if="exam" class="grid gap-3">
    <p>{{ t('study.examPacing', { days: exam.days_left, suggested: exam.suggested_daily_new, remaining: exam.remaining_new, capacity: exam.capacity, buffer: exam.buffer_capacity }) }}</p>
    <NAlert v-if="exam.days_left === 0" type="warning">
      {{ t('study.examPast') }}
    </NAlert>
    <NAlert v-if="exam.impossible" type="warning">
      {{ t('study.examImpossible') }}
    </NAlert>
    <NAlert v-if="exam.buffer_at_risk" type="warning">
      {{ t('study.examBuffer') }}
    </NAlert>
  </div>
  <p v-else class="text-muted">
    {{ t('study.noExam') }}
  </p>
</template>
