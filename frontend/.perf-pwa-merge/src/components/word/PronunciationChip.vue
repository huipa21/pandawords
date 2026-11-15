<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AudioButton from './AudioButton.vue'

defineProps<{ ipa: string, accent: 'US' | 'UK', audioUrl?: string, disabled?: boolean, playbackState?: 'playing' | 'stopped' }>()
const emit = defineEmits<{ play: [src: string | undefined] }>()
const { t } = useI18n()
</script>

<template>
  <span class="max-w-full inline-flex flex-wrap items-center gap-2 border border-base rounded-full bg-surface px-3">
    <span class="text-sm text-muted">{{ t(`word.accent.${accent}`) }}</span>
    <span lang="en-fonipa" class="min-w-0 break-words font-ipa">/{{ ipa }}/</span>
    <AudioButton :src="audioUrl" :disabled="disabled" :playback-state="playbackState" @play="emit('play', $event)" />
  </span>
</template>
