<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/app/PageHeader.vue'
import GraphExplorer from './GraphExplorer.vue'

const { t } = useI18n()
</script>

<template>
  <section class="space-y-6" data-testid="all-words">
    <PageHeader :title="t('pages.words')" />
    <GraphExplorer />
  </section>
</template>
