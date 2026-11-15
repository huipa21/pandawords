<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/app/PageHeader.vue'
import UserBackupSection from '@/features/portability/UserBackupSection.vue'

const { t } = useI18n()
</script>

<template>
  <section class="mx-auto max-w-content grid gap-6" data-testid="settings-page">
    <PageHeader :title="t('pages.settings')" />
    <UserBackupSection />
  </section>
</template>
