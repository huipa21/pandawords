<script setup lang="ts">
import { darkTheme, dateEnUS, dateZhCN, enUS, zhCN } from 'naive-ui'
import { watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { darkThemeOverrides, themeOverrides } from '@/design/naive-theme'
import { usePreferencesStore } from '@/stores/preferences'

const preferences = usePreferencesStore()
const { locale, t } = useI18n({ useScope: 'global' })

watchEffect(() => {
  locale.value = preferences.locale
  document.documentElement.lang = preferences.locale
  document.documentElement.dataset.theme = preferences.resolvedTheme
  document.title = t('app.name')
})
</script>

<template>
  <NConfigProvider
    class="font-sans text-base leading-normal"
    :theme="preferences.resolvedTheme === 'dark' ? darkTheme : null"
    :theme-overrides="preferences.resolvedTheme === 'dark' ? darkThemeOverrides : themeOverrides"
    :locale="preferences.locale === 'en' ? enUS : zhCN"
    :date-locale="preferences.locale === 'en' ? dateEnUS : dateZhCN"
  >
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider>
          <RouterView />
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
}

body {
  margin: var(--pw-space-0);
}
</style>
