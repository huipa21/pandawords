<script setup lang="ts">
import type { FormInst, FormRules } from 'naive-ui'
import type { components } from '@/api/schema'
import { useMessage } from 'naive-ui'
import { computed, reactive, ref, useTemplateRef } from 'vue'
import PageHeader from '@/components/app/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import ChangePasswordPage from './ChangePasswordPage.vue'
import ProfileAvatar from './ProfileAvatar.vue'
import { useAuthForm } from './useAuthForm'

const auth = useAuthStore()
const message = useMessage()
const form = useTemplateRef<FormInst>('form')
const avatarInput = useTemplateRef<HTMLInputElement>('avatarInput')
const { t, loading, errors, submit } = useAuthForm(form)
const readingAvatar = ref(false)
const model = reactive<components['schemas']['ProfileUpdate']>({
  avatar: auth.user?.avatar ?? '',
  email: auth.user?.email ?? '',
  full_name: auth.user?.full_name ?? '',
})
const rules = computed<FormRules>(() => ({
  email: {
    validator: (_, value: string) => !value.trim() || /^[^\s@]+@[^\s@][^\s.@]*\.[^\s@]+$/.test(value.trim()),
    message: t('profile.invalidEmail'),
    trigger: ['input', 'blur'],
  },
}))

async function selectAvatar(event: Event) {
  const input = event.target
  if (!(input instanceof HTMLInputElement))
    return
  const file = input.files?.[0]
  input.value = ''
  if (!file)
    return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 256 * 1024 || file.size === 0) {
    message.error(t('profile.avatarHint'))
    return
  }
  readingAvatar.value = true
  try {
    model.avatar = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => typeof reader.result === 'string'
        ? resolve(reader.result)
        : reject(new Error('Invalid avatar file'))
      reader.onerror = () => reject(reader.error)
      reader.onabort = () => reject(new Error('Avatar read aborted'))
      reader.readAsDataURL(file)
    })
  }
  catch {
    message.error(t('profile.avatarFailed'))
  }
  finally {
    readingAvatar.value = false
  }
}

function save() {
  if (readingAvatar.value)
    return
  return submit(async () => {
    await auth.updateProfile(model)
    model.email = auth.user?.email ?? ''
    model.full_name = auth.user?.full_name ?? ''
    message.success(t('profile.saved'))
  }, ['email', 'full_name', 'avatar'])
}
</script>

<template>
  <section class="mx-auto max-w-content grid gap-6" data-testid="profile-page">
    <PageHeader :title="t('profile.title')" />
    <NForm ref="form" size="large" :model="model" :rules="rules" :disabled="loading || readingAvatar" @submit.prevent="save">
      <NFormItem path="avatar" :label="t('profile.avatar')" :label-props="{ for: 'profile-avatar' }" :feedback="errors.avatar" :validation-status="errors.avatar ? 'error' : undefined">
        <div class="grid w-full gap-2">
          <ProfileAvatar :name="model.full_name || auth.user?.username || ''" :avatar="model.avatar" />
          <input id="profile-avatar" ref="avatarInput" type="file" accept="image/png,image/jpeg,image/webp" :disabled="loading || readingAvatar" class="hidden" @change="selectAvatar">
          <NButton size="large" class="justify-self-start" :loading="readingAvatar" :disabled="loading || readingAvatar" aria-describedby="avatar-hint" @click="avatarInput?.click()">
            {{ t('profile.chooseAvatar') }}
          </NButton>
          <p id="avatar-hint" class="text-sm text-muted">
            {{ t('profile.avatarHint') }}
          </p>
          <NButton v-if="model.avatar" size="large" class="justify-self-start" :disabled="loading || readingAvatar" @click="model.avatar = ''">
            {{ t('profile.removeAvatar') }}
          </NButton>
        </div>
      </NFormItem>
      <NFormItem :label="t('profile.userId')" :label-props="{ for: 'profile-id' }">
        <NInput :value="auth.user?.id" readonly :input-props="{ id: 'profile-id' }" />
      </NFormItem>
      <NFormItem :label="t('auth.username')" :label-props="{ for: 'profile-username' }">
        <NInput :value="auth.user?.username" readonly :input-props="{ id: 'profile-username', autocomplete: 'username' }" />
      </NFormItem>
      <NFormItem path="email" :label="t('profile.email')" :label-props="{ for: 'profile-email' }" :feedback="errors.email" :validation-status="errors.email ? 'error' : undefined">
        <NInput v-model:value="model.email" :maxlength="254" :input-props="{ id: 'profile-email', autocomplete: 'email', type: 'email' }" />
      </NFormItem>
      <NFormItem path="full_name" :label="t('profile.fullName')" :label-props="{ for: 'profile-name' }" :feedback="errors.full_name" :validation-status="errors.full_name ? 'error' : undefined">
        <NInput v-model:value="model.full_name" :maxlength="128" :input-props="{ id: 'profile-name', autocomplete: 'name' }" />
      </NFormItem>
      <NButton type="primary" size="large" attr-type="submit" :loading="loading" :disabled="loading || readingAvatar">
        {{ t('profile.save') }}
      </NButton>
    </NForm>
    <ChangePasswordPage embedded />
  </section>
</template>
