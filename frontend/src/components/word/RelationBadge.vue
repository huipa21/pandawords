<script setup lang="ts">
import type { RelationType } from './types'
import { useI18n } from 'vue-i18n'

defineProps<{ type: RelationType }>()
const { t } = useI18n()
</script>

<template>
  <NTag round :style="{ color: `var(--pw-edge-${type})` }">
    {{ t(`word.relation.${type}`) }}
  </NTag>
</template>
