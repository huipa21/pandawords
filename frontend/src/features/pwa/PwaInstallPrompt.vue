<script setup lang="ts">
import type { InstallEvent } from './install'
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { clearInstallPrompt, subscribeToInstallAvailability } from './install'

const storageKey = 'pandawords.install-dismissed.v1'
const { t } = useI18n()
const deferred = shallowRef<InstallEvent>()
const actions = ref<HTMLElement>()
const busy = ref(false)
const dismissed = ref(false)
const installFailed = ref(false)
const standalone = window.matchMedia?.('(display-mode: standalone)')
const installed = ref(standalone?.matches ?? false)
const visible = computed(() => (Boolean(deferred.value) || installFailed.value) && !dismissed.value && !installed.value)
let unsubscribe: (() => void) | undefined

function remember() {
  dismissed.value = true
  deferred.value = undefined
  installFailed.value = false
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
  let focusDismiss = false
  try {
    await event.prompt()
    const choice = await event.userChoice
    if (choice.outcome === 'accepted' || choice.outcome === 'dismissed')
      remember()
  }
  catch {
    if (!dismissed.value && !installed.value && deferred.value === event) {
      focusDismiss = document.activeElement === actions.value?.querySelector('button')
      installFailed.value = true
    }
  }
  finally {
    clearInstallPrompt(event)
    if (deferred.value === event)
      deferred.value = undefined
    busy.value = false
  }
  if (focusDismiss) {
    await nextTick()
    if (installFailed.value && !deferred.value && document.activeElement === document.body)
      actions.value?.querySelector<HTMLButtonElement>('button')?.focus()
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
      if (availability.event)
        installFailed.value = false
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
        <p v-if="installFailed" role="alert" class="mb-0 mt-1 text-sm text-error">
          {{ t('pwa.installFailed') }}
        </p>
      </div>
      <div ref="actions" class="flex flex-wrap gap-2">
        <NButton v-if="deferred" type="primary" size="large" class="focus-visible:pw-focus-ring" :loading="busy" @click="install">
          {{ t('pwa.install') }}
        </NButton>
        <NButton size="large" class="focus-visible:pw-focus-ring" :disabled="busy" @click="remember">
          {{ t('pwa.dismiss') }}
        </NButton>
      </div>
    </div>
  </section>
</template>
