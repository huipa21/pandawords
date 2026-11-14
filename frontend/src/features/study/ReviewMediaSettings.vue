<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import ErrorState from '@/components/app/ErrorState.vue'
import { useStudyResource } from './useStudyResource'

const { t } = useI18n()
const { data, loading, error, load } = useStudyResource(
  () => 'review-media',
  () => api.GET('/api/auth/me/review-preferences'),
)
const model = reactive({ review_images_enabled: true, review_audio_enabled: true, accent: 'US' as 'US' | 'UK' })
const busy = ref(false)
const failed = ref(false)
const saved = ref(false)
watch(data, (value) => {
  if (value)
    Object.assign(model, value)
})
async function save() {
  if (busy.value)
    return
  busy.value = true
  failed.value = false
  saved.value = false
  try {
    const result = await api.PATCH('/api/auth/me/review-preferences', {
      body: { ...model },
    })
    if (!result.data)
      throw new Error('unavailable')
    Object.assign(model, result.data)
    saved.value = true
  }
  catch {
    failed.value = true
  }
  finally {
    busy.value = false
  }
}
</script>

<template>
  <NCard :title="t('session.mediaSettings')" data-testid="review-media-settings">
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="3" />
    </div>
    <ErrorState v-else-if="error" :error="error" @retry="load" />
    <NForm v-else-if="data" label-placement="top" @submit.prevent="save">
      <p class="mb-4 text-muted">
        {{ t('session.mediaNotice') }}
      </p>
      <NFormItem :label="t('session.imagesEnabled')">
        <NSwitch v-model:value="model.review_images_enabled" size="large" class="min-h-12 min-w-12" :disabled="busy" :aria-label="t('session.imagesEnabled')" />
      </NFormItem>
      <NFormItem :label="t('session.audioEnabled')">
        <NSwitch v-model:value="model.review_audio_enabled" size="large" class="min-h-12 min-w-12" :disabled="busy" :aria-label="t('session.audioEnabled')" />
      </NFormItem>
      <NFormItem :label="t('session.accent')">
        <NRadioGroup v-model:value="model.accent" size="large" :disabled="busy" :aria-label="t('session.accent')">
          <NRadioButton value="US" class="min-h-12">
            {{ t('session.accentUS') }}
          </NRadioButton>
          <NRadioButton value="UK" class="min-h-12">
            {{ t('session.accentUK') }}
          </NRadioButton>
        </NRadioGroup>
      </NFormItem>
      <NAlert v-if="failed" type="error" role="alert" class="mb-4">
        {{ t('errors.transport') }}
      </NAlert>
      <p v-if="saved" role="status" class="mb-4">
        {{ t('study.saved') }}
      </p>
      <NButton size="large" type="primary" attr-type="submit" :loading="busy" :disabled="busy">
        {{ t('session.saveMedia') }}
      </NButton>
    </NForm>
  </NCard>
</template>
