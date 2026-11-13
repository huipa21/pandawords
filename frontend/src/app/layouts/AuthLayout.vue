<script setup lang="ts">
import AppHeader from '@/components/app/AppHeader.vue'
</script>

<template>
  <div class="min-h-screen flex flex-col bg-page text-fg">
    <AppHeader />
    <main class="mx-auto w-full max-w-reading flex-1 p-4 lg:p-6">
      <RouterView />
    </main>
  </div>
</template>
