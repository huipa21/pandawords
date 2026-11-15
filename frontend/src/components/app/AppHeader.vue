<script setup lang="ts">
import { NButton, NDropdown, useMessage } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { layout } from '@/design/tokens'
import { AuthRequestError, errorKey } from '@/features/auth/errors'
import ProfileAvatar from '@/features/auth/ProfileAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import LocaleSwitch from './LocaleSwitch.vue'
import ThemeToggle from './ThemeToggle.vue'

const { t, te } = useI18n()
const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const loggingOut = ref(false)
const showAccount = ref(false)
const accountOptions = computed(() => [
  {
    key: 'profile',
    label: t('profile.title'),
  },
  {
    key: 'logout',
    label: t('auth.logout'),
    disabled: loggingOut.value,
  },
])

async function selectAccount(key: string) {
  if (key === 'profile')
    await router.push('/profile')
  else if (key === 'logout')
    await logout()
}

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
  <header class="flex w-full shrink-0 flex-wrap items-center justify-between gap-2 rounded-lg border border-base bg-surface px-4 py-1 shadow-1 lg:px-6">
    <RouterLink to="/projects" class="flex shrink-0 items-center rounded-sm text-lg text-fg font-semibold no-underline focus-visible:pw-focus-ring">
      <span aria-hidden="true" class="mr-2 inline-flex h-8 w-8 items-center justify-center rounded-md bg-primary text-on-primary">
        <i-lucide-panda />
      </span>
      <span>{{ t('app.name') }}</span>
    </RouterLink>
    <div class="flex shrink-0 flex-wrap items-center justify-end gap-2">
      <LocaleSwitch />
      <ThemeToggle />
      <NDropdown v-if="auth.accessToken" v-model:show="showAccount" trigger="click" size="large" :menu-props="() => ({ role: 'menu' })" :node-props="() => ({ role: 'menuitem' })" :theme-overrides="{ optionHeightLarge: layout.touchTarget }" :options="accountOptions" @select="selectAccount">
        <NButton size="large" circle quaternary aria-haspopup="menu" :aria-expanded="showAccount" :aria-label="t('profile.accountMenu')" :title="t('profile.accountMenu')" :loading="loggingOut" :disabled="loggingOut">
          <ProfileAvatar :name="auth.user?.full_name || auth.user?.username || ''" :avatar="auth.user?.avatar" />
        </NButton>
      </NDropdown>
    </div>
  </header>
</template>

<style scoped>
header {
  min-height: var(--pw-layout-header-height);
}
</style>
