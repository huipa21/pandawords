<script setup lang="ts">
defineProps<{ title: string, subtitle?: string }>()
</script>

<template>
  <header class="flex flex-wrap items-center justify-between gap-4">
    <div class="min-w-0">
      <h1 class="m-0 break-words text-xl font-semibold">
        {{ title }}
      </h1>
      <p v-if="subtitle" class="mb-0 text-muted">
        {{ subtitle }}
      </p>
    </div>
    <div v-if="$slots.actions" class="flex flex-wrap items-center gap-3">
      <slot name="actions" />
    </div>
  </header>
</template>
