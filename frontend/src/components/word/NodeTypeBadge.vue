<script setup lang="ts">
import type { NodeType } from './types'
import { useI18n } from 'vue-i18n'

defineProps<{ type: NodeType }>()
const { t } = useI18n()
</script>

<template>
  <NTag round :style="{ color: `var(--pw-node-${type})` }">
    {{ t(`word.node.${type}`) }}
  </NTag>
</template>
