<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import { formatBytes } from '@/features/portability/archive'
import { usePortabilityI18n } from '@/features/portability/messages'
import { useSiteBackups } from './useSiteBackups'

const { t, te, locale } = usePortabilityI18n()
const when = (value: string) => new Intl.DateTimeFormat(locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
const { status, loading, starting, loadError, actionError, processing, load, start, downloadSelected, deleteSelected, cancelDownload } = useSiteBackups()
const running = computed(() => status.value?.running ?? false)
const selected = ref<string[]>([])
const confirmingDelete = ref(false)
const restoreMode = ref<'' | 'import' | 'restore'>('')
const restoreName = ref('')
const backups = computed(() => status.value?.backups ?? [])
const allSelected = computed(() => backups.value.length > 0 && selected.value.length === backups.value.length)
const busy = computed(() => Boolean(processing.value) || starting.value)
watch(backups, (items) => {
  const names = new Set(items.map(item => item.name))
  selected.value = selected.value.filter(name => names.has(name))
})
function selectAll(checked: boolean) {
  selected.value = checked
    ? backups.value.map(backup => backup.name)
    : []
}
function select(name: string, checked: boolean) {
  selected.value = checked
    ? [...selected.value, name]
    : selected.value.filter(item => item !== name)
}
function showRestore() {
  const [name] = selected.value
  if (selected.value.length !== 1 || !name)
    return
  restoreName.value = name
  restoreMode.value = 'restore'
}
function confirmDelete() {
  actionError.value = ''
  confirmingDelete.value = true
}
async function removeSelected() {
  if (await deleteSelected([...selected.value]))
    confirmingDelete.value = false
}
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
        <NButton size="large" :disabled="loading || busy" :aria-label="t('common.refresh')" :title="t('common.refresh')" @click="load">
          <template #icon>
            <i-lucide-refresh-cw aria-hidden="true" />
          </template>
        </NButton>
        <NButton size="large" type="primary" :loading="starting" :disabled="busy || running || !status" :aria-label="t('siteBackup.export')" :title="t('siteBackup.export')" data-testid="site-backup-start" @click="start">
          <template #icon>
            <i-lucide-file-output aria-hidden="true" />
          </template>
        </NButton>
        <NButton size="large" :disabled="busy" :aria-label="t('siteBackup.import')" :title="t('siteBackup.import')" data-testid="site-backup-import" @click="restoreMode = 'import'">
          <template #icon>
            <i-lucide-file-input aria-hidden="true" />
          </template>
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
    <NAlert v-if="loadError && status" type="error">
      {{ loadError }}
    </NAlert>
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
    <div v-if="status" class="flex flex-wrap items-center gap-3 border-b border-base pb-3" role="group" :aria-label="t('siteBackup.actions')">
      <NCheckbox
        size="large" class="backup-checkbox items-center"
        :checked="allSelected" :indeterminate="selected.length > 0 && !allSelected"
        :disabled="busy || !backups.length" :aria-label="t('siteBackup.selectAll')"
        data-testid="site-backup-select-all" @update:checked="selectAll"
      >
        {{ t('siteBackup.selected', { count: selected.length }) }}
      </NCheckbox>
      <NButton size="large" :disabled="!selected.length || busy" :loading="processing === 'download'" data-testid="site-backup-download" @click="downloadSelected([...selected])">
        <template #icon>
          <i-lucide-download aria-hidden="true" />
        </template>
        {{ t('siteBackup.download') }}
      </NButton>
      <NButton size="large" type="error" :disabled="!selected.length || busy || running" data-testid="site-backup-delete" @click="confirmDelete">
        <template #icon>
          <i-lucide-trash-2 aria-hidden="true" />
        </template>
        {{ t('siteBackup.delete') }}
      </NButton>
      <NButton size="large" :disabled="selected.length !== 1 || busy || running" data-testid="site-backup-restore" @click="showRestore">
        <template #icon>
          <i-lucide-rotate-ccw aria-hidden="true" />
        </template>
        {{ t('siteBackup.restore') }}
      </NButton>
      <NButton v-if="processing === 'download'" size="large" @click="cancelDownload">
        {{ t('common.cancel') }}
      </NButton>
    </div>
    <EmptyState v-if="status && !status.backups.length" title-key="siteBackup.empty" />
    <ul v-if="status?.backups.length" class="m-0 grid list-none gap-4 p-0" :aria-label="t('siteBackup.list')">
      <li v-for="backup in status.backups" :key="backup.name" class="flex items-center gap-3 border border-base rounded-lg bg-raised p-4">
        <NCheckbox
          size="large" class="backup-checkbox shrink-0 items-center"
          :checked="selected.includes(backup.name)" :disabled="busy"
          :aria-label="t('siteBackup.selectNamed', { name: backup.name })"
          data-testid="site-backup-select" @update:checked="select(backup.name, $event)"
        />
        <div class="min-w-0 grid gap-1">
          <span class="break-all font-semibold">{{ backup.name }}</span>
          <span class="text-sm text-muted">
            {{ t('siteBackup.meta', { date: when(backup.created_at), size: formatBytes(backup.size) }) }}
          </span>
        </div>
      </li>
    </ul>
    <ConfirmAction
      :show="confirmingDelete" title-key="siteBackup.deleteTitle"
      :content-key="actionError ? 'siteBackup.deleteFailed' : 'siteBackup.deleteConfirm'"
      :params="{ count: String(selected.length), error: actionError }" :loading="processing === 'delete'"
      @confirm="removeSelected" @cancel="confirmingDelete = false"
    />
    <NModal
      :show="Boolean(restoreMode)" preset="dialog" type="warning"
      :title="t(restoreMode === 'import' ? 'siteBackup.import' : 'siteBackup.restore')"
      :positive-text="t('siteBackup.close')" @positive-click="restoreMode = ''" @update:show="restoreMode = ''"
    >
      <div class="grid gap-3">
        <p class="m-0">
          {{ t('siteBackup.restoreNotice') }}
        </p>
        <p class="m-0">
          {{ t(restoreMode === 'import' ? 'siteBackup.importSteps' : 'siteBackup.restoreSteps') }}
        </p>
        <code v-if="restoreMode === 'restore'" class="break-all">{{ restoreName }}</code>
        <code class="break-all">{{ t('siteBackup.restoreCommand') }}</code>
      </div>
    </NModal>
  </section>
</template>

<style scoped>
.backup-checkbox {
  min-width: var(--pw-layout-touch-target);
  min-height: var(--pw-layout-touch-target);
}
</style>
