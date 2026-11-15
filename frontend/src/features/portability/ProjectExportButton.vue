<script setup lang="ts">
import { useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { exportProject } from './requests'
import { useArchiveDownload } from './useArchiveDownload'

const props = defineProps<{ projectId: string }>()
const { t } = useI18n()
const message = useMessage()
const { busy, error, skipped, download, cancel } = useArchiveDownload('project.pandawords-project.tar.gz')

async function run() {
  if (await download(signal => exportProject(props.projectId, signal))) {
    message.success(t('portability.project.exported'), { duration: 3000 })
    if (skipped.value)
      message.warning(t('portability.skippedMedia', { count: skipped.value }))
  }
  else if (error.value) {
    message.error(error.value.text)
  }
}
</script>

<template>
  <NButton size="large" :loading="busy" :disabled="busy" data-testid="project-export" @click="run">
    <template #icon>
      <i-lucide-download aria-hidden="true" />
    </template>
    {{ t(busy ? 'portability.exporting' : 'portability.project.export') }}
  </NButton>
  <NButton v-if="busy" size="large" data-testid="project-export-cancel" @click="cancel">
    {{ t('common.cancel') }}
  </NButton>
</template>
