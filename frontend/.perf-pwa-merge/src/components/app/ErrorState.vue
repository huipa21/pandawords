<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ error: string, loading?: boolean }>()
defineEmits<{ retry: [] }>()
const { t } = useI18n()
</script>

<template>
  <NResult status="error" :title="t('common.loadFailed')" :description="error">
    <template #footer>
      <NButton size="large" :loading="loading" @click="$emit('retry')">
        {{ t('common.retry') }}
      </NButton>
    </template>
  </NResult>
</template>
