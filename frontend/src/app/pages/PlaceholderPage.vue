<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import LocaleSwitch from '@/components/app/LocaleSwitch.vue'
import ThemeToggle from '@/components/app/ThemeToggle.vue'

const route = useRoute()
const { t } = useI18n()
</script>

<template>
  <section class="flex flex-col gap-6">
    <h1 class="m-0 text-2xl font-semibold">
      {{ t(`pages.${String(route.meta.title)}`) }}
    </h1>
    <NCard>
      <p class="m-0 text-muted">
        {{ t('app.placeholder') }}
      </p>
      <div v-if="route.name === 'design'" class="mt-4 flex gap-2">
        <ThemeToggle />
        <LocaleSwitch />
      </div>
    </NCard>
  </section>
</template>
