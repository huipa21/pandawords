<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePreferencesStore } from '@/stores/preferences'

const preferences = usePreferencesStore()
const { t } = useI18n()
</script>

<template>
  <NButton
    quaternary circle size="large"
    :aria-label="t('preferences.themeAction', { mode: t(`preferences.${preferences.theme}`) })"
    :title="t('preferences.themeAction', { mode: t(`preferences.${preferences.theme}`) })"
    @click="preferences.theme = preferences.theme === 'light' ? 'dark' : 'light'"
  >
    <template #icon>
      <i-lucide-moon v-if="preferences.theme === 'light'" aria-hidden="true" />
      <i-lucide-sun v-else aria-hidden="true" />
    </template>
  </NButton>
</template>
