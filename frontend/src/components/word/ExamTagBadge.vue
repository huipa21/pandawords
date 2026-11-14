<script setup lang="ts">
import type { ExamTag } from './types'
import { useI18n } from 'vue-i18n'

defineProps<{ tag: ExamTag }>()
const { t } = useI18n()
</script>

<template>
  <NTag round>
    {{ t(`word.exam.${tag}`) }}
  </NTag>
</template>
