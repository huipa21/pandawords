<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = defineProps<{ name: string, avatar?: string }>()
const failed = ref(false)
watch(() => props.avatar, () => failed.value = false)
const initials = computed(() => {
  const words = props.name.trim().split(/\s+/).filter(Boolean)
  return words.slice(0, 2).map(word => Array.from(word)[0]).join('').toUpperCase()
})
</script>

<template>
  <span class="inline-flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden rounded-full bg-primary-soft text-sm text-primary font-semibold">
    <img v-if="avatar && !failed" :src="avatar" alt="" class="h-full w-full object-cover" @error="failed = true">
    <span v-else aria-hidden="true">{{ initials }}</span>
  </span>
</template>
