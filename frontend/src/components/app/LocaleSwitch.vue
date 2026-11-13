<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePreferencesStore } from '@/stores/preferences'

const preferences = usePreferencesStore()
const { t } = useI18n()
</script>

<template>
  <NButton
    quaternary circle size="large"
    :aria-label="t('preferences.localeAction')"
    :title="t('preferences.localeAction')"
    @click="preferences.locale = preferences.locale === 'zh-CN' ? 'en' : 'zh-CN'"
  >
    <template #icon>
      <i-lucide-languages aria-hidden="true" />
    </template>
  </NButton>
</template>
