<script setup lang="ts">
import { useMessage } from 'naive-ui'
import { watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { errorKey } from './errors'

const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const { t, te } = useI18n()
watch(() => auth.sessionError, (code) => {
  if (code) {
    message.error(t(te(errorKey(code))
      ? errorKey(code)
      : 'errors.generic'))
    auth.sessionError = null
  }
}, { immediate: true })
watch(() => auth.accessToken, (token) => {
  if (!token && router.currentRoute.value.name !== 'login')
    void router.replace('/login')
})
</script>

<template>
  <slot />
</template>
