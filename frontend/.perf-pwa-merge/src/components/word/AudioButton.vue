<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useWordAudio } from './audio'

const props = withDefaults(defineProps<{
  src?: string
  disabled?: boolean
  size?: 'small' | 'medium' | 'large'
  playbackState?: 'playing' | 'stopped'
}>(), { size: 'large' })
const emit = defineEmits<{ play: [src: string | undefined], error: [] }>()
const { t } = useI18n()
const owner = Symbol('audio')
const player = useWordAudio()
const playing = computed(() => props.playbackState === undefined
  ? player.active.value === owner
  : props.playbackState === 'playing')
const failed = ref(false)
function stop() {
  player.stop(owner)
}
function play() {
  if (playing.value) {
    if (props.playbackState === undefined)
      stop()
    else
      emit('play', props.src)
    return
  }
  failed.value = false
  emit('play', props.src)
  if (props.src && props.playbackState === undefined) {
    void player.play(owner, props.src, () => {
      failed.value = true
      emit('error')
    })
  }
}
watch(() => [props.src, props.disabled], () => {
  stop()
  failed.value = false
})
onBeforeUnmount(stop)
</script>

<template>
  <span class="inline-flex flex-wrap items-center gap-2">
    <NButton
      :size="size" :disabled="disabled" class="h-control-large min-w-12"
      :aria-label="t(playing ? 'word.audio.stop' : 'word.audio.play')"
      :aria-pressed="playing" @click="play"
    >
      <template #icon>
        <i-lucide-square v-if="playing" aria-hidden="true" />
        <i-lucide-volume-2 v-else aria-hidden="true" />
      </template>

    </NButton>
    <span v-if="failed" role="status" class="text-sm text-error">{{ t('word.audio.error') }}</span>
  </span>
</template>

<style scoped>
.n-button {
  min-height: var(--pw-control-height-large);
  min-width: var(--pw-control-height-large);
}
</style>
