<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import ArchiveImportForm from './ArchiveImportForm.vue'

const emit = defineEmits<{ imported: [] }>()
const show = defineModel<boolean>('show', { required: true })
const { t } = useI18n()
</script>

<template>
  <NModal
    v-model:show="show" preset="card" :title="t('portability.project.importTitle')"
    :style="{ width: 'var(--pw-layout-reading-max-width)', maxWidth: 'calc(100% - var(--pw-space-8))' }"
    data-testid="project-import-dialog"
  >
    <ArchiveImportForm kind="project" @done="emit('imported')" />
  </NModal>
</template>
