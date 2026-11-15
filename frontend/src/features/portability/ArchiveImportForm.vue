<script setup lang="ts">
import type { ImportSummary, RestoreSummary } from './requests'
import type { ProgressChoice, UploadRequest } from './useArchiveUpload'
import { computed, ref, useId } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { formatBytes, MAX_ARCHIVE_BYTES } from './archive'
import ArchiveSummary from './ArchiveSummary.vue'
import { importProject, restoreUserBackup } from './requests'
import { useArchiveUpload } from './useArchiveUpload'

const props = defineProps<{ kind: 'project' | 'user' }>()
const emit = defineEmits<{ done: [summary: ImportSummary | RestoreSummary] }>()
const { t } = useI18n()
const id = useId()
const input = ref<HTMLInputElement>()
const confirming = ref(false)
const request: UploadRequest<ImportSummary | RestoreSummary> = props.kind === 'project'
  ? importProject
  : restoreUserBackup
const upload = useArchiveUpload(request, props.kind === 'project'
  ? 'auto'
  : 'on')
const { file, problem, choice, state, summary, error } = upload
const choices = computed<ProgressChoice[]>(() => props.kind === 'project'
  ? ['auto', 'on', 'off']
  : ['on', 'off'])
const uploading = computed(() => state.value === 'uploading')

function pick(event: Event) {
  const target = event.target as HTMLInputElement
  upload.select(target.files?.[0])
  target.value = ''
}

function start() {
  if (!file.value || problem.value || uploading.value)
    return
  if (props.kind === 'user')
    confirming.value = true
  else
    void send()
}

async function send() {
  confirming.value = false
  if (await upload.submit() && summary.value)
    emit('done', summary.value)
}
</script>

<template>
  <form class="grid gap-4" :data-testid="`archive-import-${kind}`" @submit.prevent="start">
    <p class="m-0 text-muted">
      {{ t(`portability.${kind}.importHint`) }}
    </p>
    <div class="flex flex-wrap items-center gap-3">
      <input
        :id="`${id}-file`" ref="input" class="sr-only" type="file" accept=".gz,.tgz,application/gzip"
        :disabled="uploading" data-testid="archive-input" @change="pick"
      >
      <NButton size="large" :disabled="uploading" :aria-describedby="`${id}-selected`" @click="input?.click()">
        <template #icon>
          <i-lucide-file-archive aria-hidden="true" />
        </template>
        {{ t(file ? 'portability.changeFile' : 'portability.chooseFile') }}
      </NButton>
      <span :id="`${id}-selected`" class="break-all text-sm" :class="file ? '' : 'text-muted'" data-testid="archive-file">
        {{ file ? t('portability.selected', { name: file.name, size: formatBytes(file.size) }) : t('portability.noFile') }}
      </span>
    </div>
    <NAlert v-if="problem" type="warning" :show-icon="false" role="alert">
      {{ t(`portability.problems.${problem}`, { max: formatBytes(MAX_ARCHIVE_BYTES) }) }}
    </NAlert>
    <fieldset class="m-0 grid gap-2 border-0 p-0" :disabled="uploading">
      <legend class="mb-2 p-0 font-semibold">
        {{ t('portability.progress.label') }}
      </legend>
      <NRadioGroup v-model:value="choice" :name="`${id}-progress`" :disabled="uploading">
        <div class="flex flex-wrap gap-4">
          <NRadio v-for="option in choices" :key="option" :value="option" :data-testid="`progress-${option}`">
            {{ t(`portability.progress.${option}`) }}
          </NRadio>
        </div>
      </NRadioGroup>
      <p class="m-0 text-sm text-muted" data-testid="progress-hint">
        {{ t(`portability.progress.${choice}Hint`) }}
      </p>
    </fieldset>
    <div role="status" aria-live="polite" data-testid="archive-status">
      <div v-if="uploading" class="flex flex-wrap items-center gap-3">
        <NSpin size="small" :aria-label="t('common.loading')" />
        <span>{{ t('portability.uploading', { size: formatBytes(file?.size ?? 0) }) }}</span>
        <NButton size="large" data-testid="archive-cancel" @click="upload.cancel()">
          {{ t('common.cancel') }}
        </NButton>
      </div>
      <span v-else-if="state === 'cancelled'" class="text-muted">{{ t('portability.cancelled') }}</span>
    </div>
    <NAlert v-if="state === 'error' && error" type="error" :title="error.text" data-testid="archive-error">
      <p v-if="error.stage" class="m-0">
        {{ t('portability.failedStage', { stage: error.stage }) }}
      </p>
      <ul v-if="error.problems.length" class="m-0 break-words pl-4 text-sm" :aria-label="t('portability.details')">
        <li v-for="item in error.problems" :key="item">
          {{ item }}
        </li>
      </ul>
      <p class="m-0 text-sm">
        {{ t('portability.retryHint') }}
      </p>
    </NAlert>
    <ArchiveSummary v-if="state === 'success' && summary" :kind="kind" :summary="summary" />
    <div class="flex flex-wrap gap-3">
      <NButton size="large" type="primary" attr-type="submit" :disabled="!file || !!problem || uploading" data-testid="archive-submit">
        <template #icon>
          <i-lucide-upload aria-hidden="true" />
        </template>
        {{ t(state === 'error' || state === 'cancelled' ? 'common.retry' : `portability.${kind}.submit`) }}
      </NButton>
    </div>
    <ConfirmAction
      :show="confirming" title-key="portability.user.confirmTitle" content-key="portability.user.confirm"
      :params="{ name: file?.name ?? '' }" @confirm="send" @cancel="confirming = false"
    />
  </form>
</template>
