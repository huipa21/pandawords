<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import type { components } from '@/api/schema'
import { computed, reactive, useTemplateRef } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useAuthForm } from './useAuthForm'

const auth = useAuthStore()
const router = useRouter()
const form = useTemplateRef<FormInst>('form')
const { t, loading, errors, submit } = useAuthForm(form)
const model = reactive<components['schemas']['LoginRequest']>({ username: '', password: '' })
const rules = computed<FormRules>(() => ({
  username: {
    required: true,
    message: t('auth.required'),
    trigger: ['input', 'blur'],
  },
  password: {
    required: true,
    message: t('auth.required'),
    trigger: ['input', 'blur'],
  },
}))

function login() {
  return submit(async () => {
    await auth.login(model)
    model.password = ''
    await router.replace(auth.user?.must_change_password ? '/change-password' : '/projects')
  }, ['username', 'password'])
}
</script>

<template>
  <section class="flex flex-col gap-6">
    <h1 class="text-2xl font-semibold">
      {{ t('pages.login') }}
    </h1>
    <NForm ref="form" size="large" :model="model" :rules="rules" :disabled="loading" @submit.prevent="login">
      <NFormItem path="username" :label="t('auth.username')" :label-props="{ for: 'username' }" :feedback="errors.username" :validation-status="errors.username ? 'error' : undefined">
        <NInput v-model:value="model.username" :input-props="{ autocomplete: 'username', id: 'username' }" />
      </NFormItem>
      <NFormItem path="password" :label="t('auth.password')" :label-props="{ for: 'password' }" :feedback="errors.password" :validation-status="errors.password ? 'error' : undefined">
        <NInput v-model:value="model.password" type="password" show-password-on="click" :input-props="{ autocomplete: 'current-password', id: 'password' }" />
      </NFormItem>
      <NButton size="large" type="primary" attr-type="submit" :loading="loading" :disabled="loading">
        {{ t('auth.login') }}
      </NButton>
    </NForm>
  </section>
</template>
