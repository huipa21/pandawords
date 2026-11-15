<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppHeader from './AppHeader.vue'
import AppNavigation from './AppNavigation.vue'

const { t } = useI18n()
</script>

<template>
  <div class="min-h-screen flex flex-col bg-page pb-bottom-nav text-fg lg:pb-0">
    <a href="#main-content" class="sr-only focus:not-sr-only focus:pw-focus-ring">{{ t('navigation.skip') }}</a>
    <AppHeader />
    <div class="flex flex-1">
      <aside class="hidden w-sidebar shrink-0 border-r border-base bg-surface p-4 lg:block">
        <AppNavigation />
      </aside>
      <main id="main-content" tabindex="-1" class="min-w-0 flex-1 p-4 lg:p-6">
        <div class="mx-auto max-w-content">
          <RouterView />
        </div>
      </main>
    </div>
    <div class="bottom-navigation fixed inset-x-0 bottom-0 border-t border-base bg-surface lg:hidden">
      <AppNavigation mobile />
    </div>
  </div>
</template>

<style scoped>
.bottom-navigation {
  padding-bottom: env(safe-area-inset-bottom);
}
</style>
