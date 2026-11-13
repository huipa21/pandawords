<script setup lang="ts">
import { watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'

const { locale, t } = useI18n({ useScope: 'global' })

watchEffect(() => {
  document.documentElement.lang = locale.value
  document.title = t('app.name')
})
</script>

<template>
  <main>
    <h1>{{ t('app.name') }}</h1>
    <p>{{ t('app.ready') }}</p>
  </main>
</template>
