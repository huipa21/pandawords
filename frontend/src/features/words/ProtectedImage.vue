<script setup lang="ts">
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'

const props = defineProps<{ mediaId: string }>()
const { t } = useI18n()
const url = ref('')
const loading = ref(false)
const failed = ref(false)
let controller: AbortController | undefined
let generation = 0

function clear() {
  generation++
  controller?.abort()
  if (url.value)
    URL.revokeObjectURL(url.value)
  url.value = ''
}

async function load() {
  clear()
  const current = generation
  controller = new AbortController()
  loading.value = true
  failed.value = false
  try {
    const result = await api.GET('/api/media/{rid}', {
      params: {
        path: { rid: props.mediaId },
      },
      parseAs: 'blob',
      signal: controller.signal,
    })
    if (current !== generation)
      return
    if (!result.response.ok || !(result.data instanceof Blob) || !result.data.size)
      throw new Error('unavailable')
    url.value = URL.createObjectURL(result.data)
  }
  catch {
    if (current === generation)
      failed.value = true
  }
  finally {
    if (current === generation)
      loading.value = false
  }
}
function unavailable() {
  clear()
  failed.value = true
}
watch(() => props.mediaId, load, { immediate: true })
onScopeDispose(clear)
</script>

<template>
  <div class="grid gap-3">
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSpin />
    </div>
    <img v-if="url && !failed" :src="url" :alt="t('images.alt')" class="max-h-full max-w-full rounded-lg object-contain" @error="unavailable">
    <NAlert v-if="failed" type="warning">
      {{ t('images.unavailable') }}
      <NButton size="large" @click="load">
        {{ t('common.retry') }}
      </NButton>
    </NAlert>
  </div>
</template>
