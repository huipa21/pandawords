<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import LocaleSwitch from './LocaleSwitch.vue'
import ThemeToggle from './ThemeToggle.vue'

const { t } = useI18n()
</script>

<template>
  <header class="h-header flex shrink-0 items-center justify-between border-b border-base bg-surface px-4 lg:px-6">
    <RouterLink to="/projects" class="rounded-sm text-lg text-fg font-semibold no-underline focus-visible:pw-focus-ring">
      {{ t('app.name') }}
    </RouterLink>
    <div class="flex items-center gap-2">
      <ThemeToggle />
      <LocaleSwitch />
    </div>
  </header>
</template>
