<script setup lang="ts">
import ArchiveImportForm from './ArchiveImportForm.vue'
import { usePortabilityI18n } from './messages'
import { downloadUserBackup } from './requests'
import { useArchiveDownload } from './useArchiveDownload'

const { t } = usePortabilityI18n()
const { busy, error, skipped, savedName, download, cancel } = useArchiveDownload('pandawords-backup.pandawords-user.tar.gz')
</script>

<template>
  <div class="grid gap-6" data-testid="user-backup">
    <NCard :title="t('portability.user.backupTitle')">
      <div class="grid gap-4">
        <p class="m-0 text-muted">
          {{ t('portability.user.backupHint') }}
        </p>
        <div class="flex flex-wrap items-center gap-3">
          <NButton size="large" type="primary" :loading="busy" :disabled="busy" data-testid="user-backup-download" @click="download(downloadUserBackup)">
            <template #icon>
              <i-lucide-download aria-hidden="true" />
            </template>
            {{ t(busy ? 'portability.exporting' : 'portability.user.download') }}
          </NButton>
          <NButton v-if="busy" size="large" data-testid="user-backup-cancel" @click="cancel">
            {{ t('common.cancel') }}
          </NButton>
        </div>
        <div role="status" aria-live="polite" data-testid="user-backup-status">
          <NAlert v-if="savedName && !busy" type="success" :show-icon="false">
            {{ t('portability.user.downloaded', { name: savedName }) }}
            <template v-if="skipped">
              {{ t('portability.skippedMedia', { count: skipped }) }}
            </template>
          </NAlert>
        </div>
        <NAlert v-if="error" type="error" :title="error.text" data-testid="user-backup-error">
          {{ t('portability.retryHint') }}
        </NAlert>
      </div>
    </NCard>
    <NCard :title="t('portability.user.restoreTitle')">
      <ArchiveImportForm kind="user" />
    </NCard>
  </div>
</template>
