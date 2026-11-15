<script setup lang="ts">
import type { FormInst } from 'naive-ui'
import { computed, onScopeDispose, reactive, ref, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { normalizeApiError } from '@/api/errors'
import ErrorState from '@/components/app/ErrorState.vue'
import { useProjectErrors } from '@/features/projects/useProject'
import { useStudyResource } from './useStudyResource'

const { t } = useI18n()
const errorText = useProjectErrors()
const { data, loading, error, load } = useStudyResource(
  () => 'retention',
  () => api.GET('/api/auth/me/srs-preferences'),
)
const form = useTemplateRef<FormInst>('form')
const model = reactive<{ retention: number | null }>({ retention: null })
const busy = ref(false)
const saveError = ref('')
const fieldError = ref('')
const saved = ref(false)
let disposed = false
watch(data, value => model.retention = value?.desired_retention ?? null)
onScopeDispose(() => disposed = true)
const rules = computed(() => ({
  retention: {
    validator: () => model.retention !== null && Number.isFinite(model.retention) && model.retention > 0 && model.retention < 1,
    message: t('study.retentionValidation'),
    trigger: ['blur', 'change'],
  },
}))

async function save() {
  if (busy.value)
    return
  saved.value = false
  saveError.value = ''
  fieldError.value = ''
  try {
    await form.value?.validate()
  }
  catch {
    return
  }
  if (disposed || busy.value || model.retention === null)
    return
  busy.value = true
  try {
    const result = await api.PATCH('/api/auth/me/srs-preferences', {
      body: { desired_retention: model.retention },
    })
    if (disposed)
      return
    if (result.data) {
      model.retention = result.data.desired_retention
      saved.value = true
    }
    else {
      const error = normalizeApiError(result.error, result.response.status)
      if (error.field === 'desired_retention')
        fieldError.value = errorText(error, result.response.status)
      else
        saveError.value = errorText(error, result.response.status)
    }
  }
  catch {
    if (!disposed)
      saveError.value = t('errors.transport')
  }
  finally {
    if (!disposed)
      busy.value = false
  }
}
</script>

<template>
  <NCard :title="t('study.userSettings')">
    <p class="mb-4 text-muted">
      {{ t('study.retentionNotice') }}
    </p>
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="2" />
    </div>
    <ErrorState v-else-if="error" :error="error" @retry="load" />
    <NForm v-else-if="data" ref="form" :model="model" :rules="rules" label-placement="top" data-testid="retention-form" @submit.prevent="save">
      <NFormItem
        path="retention" :label="t('study.desiredRetention')" :label-props="{ for: 'desired-retention' }"
        :validation-status="fieldError ? 'error' : undefined" :feedback="fieldError"
      >
        <NInputNumber
          v-model:value="model.retention" size="large" :disabled="busy" :show-button="false"
          :input-props="{ 'id': 'desired-retention', 'aria-describedby': 'retention-help' }"
        />
      </NFormItem>
      <p id="retention-help" class="mb-4 text-sm text-muted">
        {{ t('study.retentionHelp') }}
      </p>
      <NAlert v-if="saveError" type="error" class="mb-4" role="alert">
        {{ saveError }}
      </NAlert>
      <p v-if="saved" role="status" class="mb-4">
        {{ t('study.saved') }}
      </p>
      <NButton size="large" type="primary" attr-type="submit" :loading="busy" :disabled="busy">
        {{ t('study.saveRetention') }}
      </NButton>
    </NForm>
  </NCard>
</template>
