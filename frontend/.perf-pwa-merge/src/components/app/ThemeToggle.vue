<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePreferencesStore } from '@/stores/preferences'

const preferences = usePreferencesStore()
const { t } = useI18n()
const modes = ['system', 'light', 'dark'] as const

function cycleTheme() {
  preferences.theme = modes[(modes.indexOf(preferences.theme) + 1) % modes.length]!
}
</script>

<template>
  <NButton
    quaternary circle size="large"
    :aria-label="t('preferences.themeAction', { mode: t(`preferences.${preferences.theme}`) })"
    :title="t('preferences.themeAction', { mode: t(`preferences.${preferences.theme}`) })"
    @click="cycleTheme"
  >
    <template #icon>
      <i-lucide-monitor v-if="preferences.theme === 'system'" aria-hidden="true" />
      <i-lucide-sun v-else-if="preferences.theme === 'light'" aria-hidden="true" />
      <i-lucide-moon v-else aria-hidden="true" />
    </template>
  </NButton>
</template>
