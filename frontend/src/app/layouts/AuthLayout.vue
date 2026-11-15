<script setup lang="ts">
import AppHeader from '@/components/app/AppHeader.vue'
</script>

<template>
  <div class="min-h-screen flex flex-col gap-4 bg-page p-4 text-fg lg:gap-6 lg:p-6">
    <AppHeader />
    <main class="mx-auto w-full max-w-reading flex-1">
      <RouterView />
    </main>
  </div>
</template>
