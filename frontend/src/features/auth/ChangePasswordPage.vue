<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import type { components } from '@/api/schema'
import { useMessage } from 'naive-ui'
import { computed, reactive, useTemplateRef } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAuthForm } from './useAuthForm'

const props = defineProps<{ embedded?: boolean }>()
const auth = useAuthStore()
const router = useRouter()
const message = useMessage()
const form = useTemplateRef<FormInst>('form')
const { t, loading, errors, submit } = useAuthForm(form)
const model = reactive<components['schemas']['PasswordChange']>({ current_password: '', new_password: '' })
const rules = computed<FormRules>(() => ({
  current_password: {
    required: true,
    message: t('auth.required'),
    trigger: ['input', 'blur'],
  },
  new_password: [
    {
      required: true,
      message: t('auth.required'),
      trigger: ['input', 'blur'],
    },
    {
      min: 10,
      max: 1024,
      message: t('auth.passwordLength'),
      trigger: ['input', 'blur'],
    },
  ],
}))

function changePassword() {
  return submit(async () => {
    await auth.changePassword(model)
    model.current_password = ''
    model.new_password = ''
    message.success(t('auth.passwordChanged'), { duration: 2000 })
    if (!props.embedded)
      await router.replace('/projects')
  }, ['current_password', 'new_password'])
}
</script>

<template>
  <section class="flex flex-col gap-6">
    <component :is="embedded ? 'h2' : 'h1'" class="text-2xl font-semibold">
      {{ t('pages.changePassword') }}
    </component>
    <p v-if="auth.user?.must_change_password" class="text-muted">
      {{ t('auth.changeRequired') }}
    </p>
    <NForm ref="form" size="large" :model="model" :rules="rules" :disabled="loading" @submit.prevent="changePassword">
      <NFormItem path="current_password" :label="t('auth.currentPassword')" :label-props="{ for: 'current_password' }" :feedback="errors.current_password" :validation-status="errors.current_password ? 'error' : undefined">
        <NInput v-model:value="model.current_password" type="password" show-password-on="click" :input-props="{ autocomplete: 'current-password', id: 'current_password' }" />
      </NFormItem>
      <NFormItem path="new_password" :label="t('auth.newPassword')" :label-props="{ for: 'new_password' }" :feedback="errors.new_password" :validation-status="errors.new_password ? 'error' : undefined">
        <NInput v-model:value="model.new_password" type="password" show-password-on="click" :input-props="{ autocomplete: 'new-password', id: 'new_password' }" />
      </NFormItem>
      <NButton size="large" type="primary" attr-type="submit" :loading="loading" :disabled="loading">
        {{ t('auth.changePassword') }}
      </NButton>
    </NForm>
  </section>
</template>
