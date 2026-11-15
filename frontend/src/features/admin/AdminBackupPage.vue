<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import { formatBytes } from '@/features/portability/archive'
import { useSiteBackups } from './useSiteBackups'

const { t, te, locale } = useI18n()
const when = (value: string) => new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const { status, loading, starting, loadError, actionError, downloading, load, start, download, cancelDownload } = useSiteBackups()
const running = computed(() => status.value?.running ?? false)
const lastError = computed(() => {
  const stage = status.value?.last_error
  if (!stage)
    return ''
  return t('siteBackup.failed', {
    stage: te(`siteBackup.stages.${stage}`)
      ? t(`siteBackup.stages.${stage}`)
      : t('siteBackup.stages.internal'),
  })
})

onMounted(load)
</script>

<template>
  <section class="mx-auto max-w-content grid gap-6" data-testid="admin-backup-page">
    <PageHeader :title="t('pages.backup')" :subtitle="t('siteBackup.hint')">
      <template #actions>
        <NButton size="large" :disabled="loading || starting" @click="load">
          {{ t('common.refresh') }}
        </NButton>
        <NButton size="large" type="primary" :loading="starting" :disabled="starting || running || !status" data-testid="site-backup-start" @click="start">
          <template #icon>
            <i-lucide-archive aria-hidden="true" />
          </template>
          {{ t('siteBackup.start') }}
        </NButton>
      </template>
    </PageHeader>
    <p class="m-0 text-sm text-muted">
      {{ t('siteBackup.restoreNotice') }}
    </p>
    <div v-if="loading && !status" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="3" />
    </div>
    <ErrorState v-if="loadError && !status" :error="loadError" :loading="loading" @retry="load" />
    <div role="status" aria-live="polite" data-testid="site-backup-status">
      <NAlert v-if="running" type="info" :show-icon="false">
        <span class="flex items-center gap-3">
          <NSpin size="small" :aria-label="t('common.loading')" />
          {{ t('siteBackup.running') }}
        </span>
      </NAlert>
      <NAlert v-else-if="lastError" type="error">
        {{ lastError }}
      </NAlert>
    </div>
    <NAlert v-if="actionError" type="error" data-testid="site-backup-error">
      {{ actionError }}
    </NAlert>
    <EmptyState v-if="status && !status.backups.length" title-key="siteBackup.empty" />
    <ul v-if="status?.backups.length" class="m-0 grid list-none gap-4 p-0" :aria-label="t('siteBackup.list')">
      <li v-for="backup in status.backups" :key="backup.name" class="flex flex-wrap items-center justify-between gap-3 border border-base rounded-lg bg-raised p-4">
        <div class="grid gap-1">
          <span class="break-all font-semibold">{{ backup.name }}</span>
          <span class="text-sm text-muted">
            {{ t('siteBackup.meta', { date: when(backup.created_at), size: formatBytes(backup.size) }) }}
          </span>
        </div>
        <div class="flex flex-wrap gap-2">
          <NButton
            size="large" :loading="downloading === backup.name" :disabled="Boolean(downloading)"
            :aria-label="t('siteBackup.downloadNamed', { name: backup.name })" data-testid="site-backup-download"
            @click="download(backup.name)"
          >
            <template #icon>
              <i-lucide-download aria-hidden="true" />
            </template>
            {{ t('siteBackup.download') }}
          </NButton>
          <NButton v-if="downloading === backup.name" size="large" @click="cancelDownload">
            {{ t('common.cancel') }}
          </NButton>
        </div>
      </li>
    </ul>
  </section>
</template>
