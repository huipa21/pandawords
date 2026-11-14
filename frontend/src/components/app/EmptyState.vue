<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ titleKey: string, descKey?: string }>()
const { t } = useI18n()
</script>

<template>
  <div class="space-y-4 py-8 text-center">
    <NEmpty :description="t(titleKey)" />
    <p v-if="descKey" class="text-muted">
      {{ t(descKey) }}
    </p>
    <slot name="action" />
  </div>
</template>
