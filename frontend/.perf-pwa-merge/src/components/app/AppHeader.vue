<script setup lang="ts">
import { NButton, useMessage } from 'naive-ui'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { AuthRequestError, errorKey } from '@/features/auth/errors'
import { useAuthStore } from '@/stores/auth'
import LocaleSwitch from './LocaleSwitch.vue'
import ThemeToggle from './ThemeToggle.vue'

const { t, te } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const loggingOut = ref(false)

async function logout() {
  loggingOut.value = true
  try {
    await auth.logout()
  }
  catch (error) {
    const key = errorKey(error instanceof AuthRequestError
      ? error.error.code
      : 'generic')
    message.error(t(te(key)
      ? key
      : 'errors.generic'))
  }
  finally {
    loggingOut.value = false
    await router.replace('/login')
  }
}
</script>

<template>
  <header class="h-header flex shrink-0 items-center justify-between border-b border-base bg-surface px-4 lg:px-6">
    <RouterLink to="/projects" class="rounded-sm text-lg text-fg font-semibold no-underline focus-visible:pw-focus-ring">
      {{ t('app.name') }}
    </RouterLink>
    <div class="flex items-center gap-2">
      <RouterLink
        v-if="auth.accessToken && !auth.user?.must_change_password" to="/change-password"
        :aria-label="t('auth.changePassword')" :title="t('auth.changePassword')"
        class="password-link flex items-center justify-center rounded-sm text-lg text-primary no-underline focus-visible:pw-focus-ring"
      >
        <i-lucide-key-round aria-hidden="true" />
      </RouterLink>
      <NButton v-if="auth.accessToken" size="large" circle quaternary :aria-label="t('auth.logout')" :title="t('auth.logout')" :loading="loggingOut" :disabled="loggingOut" @click="logout">
        <i-lucide-log-out aria-hidden="true" />
      </NButton>
      <ThemeToggle />
      <LocaleSwitch />
    </div>
  </header>
</template>

<style scoped>
.password-link {
  min-height: var(--pw-layout-touch-target);
  min-width: var(--pw-layout-touch-target);
}
</style>
