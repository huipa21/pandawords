<script setup lang="ts">
import type { AdminUpdate, AdminUser } from './useAdminUsers'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ user: AdminUser, busy: boolean }>()
const emit = defineEmits<{
  change: [user: AdminUser, body: AdminUpdate, titleKey: string]
}>()
const { t } = useI18n()
const auth = useAuthStore()
const protectedAdmin = computed(() => props.user.id === auth.user?.id
  || (props.user.role === 'admin' && !props.user.disabled
    && (!auth.isAdmin || auth.user?.disabled)))
</script>

<template>
  <div class="flex flex-wrap gap-2" :aria-label="t('admin.actionsFor', { username: user.username })">
    <NButton
      size="large" :disabled="busy || (protectedAdmin && !user.disabled)"
      @click="emit('change', user, { disabled: !user.disabled, reset_password: false }, user.disabled ? 'admin.enable' : 'admin.disable')"
    >
      {{ t(user.disabled ? 'admin.enable' : 'admin.disable') }}
    </NButton>
    <NButton size="large" :disabled="busy" @click="emit('change', user, { reset_password: true }, 'admin.reset')">
      {{ t('admin.reset') }}
    </NButton>
    <NButton
      size="large" :disabled="busy || (protectedAdmin && user.role === 'admin')"
      @click="emit('change', user, { role: user.role === 'admin' ? 'user' : 'admin', reset_password: false }, user.role === 'admin' ? 'admin.demote' : 'admin.promote')"
    >
      {{ t(user.role === 'admin' ? 'admin.demote' : 'admin.promote') }}
    </NButton>
  </div>
</template>
