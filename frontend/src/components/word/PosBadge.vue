<script setup lang="ts">
import type { PartOfSpeech } from './types'
import { useI18n } from 'vue-i18n'

defineProps<{ pos: PartOfSpeech }>()
const { t } = useI18n()
</script>

<template>
  <NTag round>
    {{ t(`word.pos.${pos}`) }}
  </NTag>
</template>
