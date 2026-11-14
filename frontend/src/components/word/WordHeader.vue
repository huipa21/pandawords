<script setup lang="ts">
import type { LemmaView } from './types'
import { useI18n } from 'vue-i18n'
import ExamTagBadge from './ExamTagBadge.vue'
import NodeTypeBadge from './NodeTypeBadge.vue'

withDefaults(defineProps<{ lemma: LemmaView, size?: 'md' | 'lg' | 'xl' }>(), { size: 'lg' })
const { t } = useI18n()
const sizes = { md: 'text-lg', lg: 'text-2xl', xl: 'text-2xl lg:text-3xl' }
</script>

<template>
  <header class="min-w-0 flex flex-wrap items-center gap-3">
    <span lang="en" class="min-w-0 max-w-full break-words font-serif" :class="sizes[size]">{{ lemma.text }}</span>
    <NodeTypeBadge :type="lemma.kind === 'phrase' ? 'phrase' : 'lemma'" />
    <span v-if="lemma.frequencyBand" class="text-sm text-muted">
      {{ t('word.frequency', { band: lemma.frequencyBand }) }}
    </span>
    <ExamTagBadge v-for="tag in lemma.examTags" :key="tag" :tag="tag" />
  </header>
</template>
