<script setup lang="ts">
import type { InstallEvent } from './install'
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { clearInstallPrompt, subscribeToInstallAvailability } from './install'

const storageKey = 'pandawords.install-dismissed.v1'
const { t } = useI18n()
const deferred = shallowRef<InstallEvent>()
const busy = ref(false)
const dismissed = ref(false)
const standalone = window.matchMedia?.('(display-mode: standalone)')
const installed = ref(standalone?.matches ?? false)
const visible = computed(() => deferred.value && !dismissed.value && !installed.value)
let unsubscribe: (() => void) | undefined

function remember() {
  dismissed.value = true
  deferred.value = undefined
  clearInstallPrompt()
  try {
    localStorage.setItem(storageKey, '1')
  }
  catch {
    // Dismissal still applies for this page when storage is disabled.
  }
}

async function install() {
  const event = deferred.value
  if (!event || busy.value)
    return
  busy.value = true
  try {
    await event.prompt()
    const choice = await event.userChoice
    if (choice.outcome === 'accepted' || choice.outcome === 'dismissed')
      remember()
  }
  catch {
    // A failed native prompt is not a user dismissal.
  }
  finally {
    clearInstallPrompt(event)
    if (deferred.value === event)
      deferred.value = undefined
    busy.value = false
  }
}

onMounted(() => {
  try {
    dismissed.value = localStorage.getItem(storageKey) === '1'
  }
  catch {
    // Install remains optional without persistent storage.
  }
  unsubscribe = subscribeToInstallAvailability((availability) => {
    if (availability.installed) {
      installed.value = true
      remember()
    }
    else if (dismissed.value || installed.value) {
      clearInstallPrompt()
    }
    else {
      deferred.value = availability.event
    }
  })
})
onUnmounted(() => unsubscribe?.())
</script>

<template>
  <section
    v-if="visible"
    aria-labelledby="pwa-install-title"
    class="border-b border-base bg-surface p-4 text-fg"
  >
    <div class="mx-auto max-w-content flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div class="min-w-0">
        <h2 id="pwa-install-title" class="m-0 text-base font-semibold">
          {{ t('pwa.installTitle') }}
        </h2>
        <p class="mb-0 mt-1 text-sm text-muted">
          {{ t('pwa.installDescription') }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <NButton type="primary" size="large" class="focus-visible:pw-focus-ring" :loading="busy" @click="install">
          {{ t('pwa.install') }}
        </NButton>
        <NButton size="large" class="focus-visible:pw-focus-ring" :disabled="busy" @click="remember">
          {{ t('pwa.dismiss') }}
        </NButton>
      </div>
    </div>
  </section>
</template>
