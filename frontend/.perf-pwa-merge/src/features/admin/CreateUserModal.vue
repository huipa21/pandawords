<script setup lang="ts">
import type { FormInst } from 'naive-ui'
import type { AdminCreate } from './useAdminUsers'
import { computed, reactive, useTemplateRef, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  show: boolean
  busy: boolean
  fieldError: string
  create: (body: AdminCreate) => Promise<boolean>
}>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const form = useTemplateRef<FormInst>('form')
const model = reactive<AdminCreate>({ username: '', role: 'user' })
const roles = computed(() => ['user', 'admin'].map(value => ({
  value,
  label: t(`admin.roles.${value}`),
})))
const rules = computed(() => ({
  username: [
    {
      required: true,
      whitespace: true,
      message: t('auth.required'),
      trigger: ['blur', 'input'],
    },
  ],
}))

watch(() => props.show, (show) => {
  if (show) {
    model.username = ''
    model.role = 'user'
  }
})

async function submit() {
  if (props.busy)
    return
  try {
    await form.value?.validate()
  }
  catch {
    return
  }
  if (await props.create({
    ...model,
    username: model.username.trim(),
  })) {
    emit('close')
  }
}
</script>

<template>
  <NModal :show="show" :mask-closable="!busy" :close-on-esc="!busy" @update:show="(value: boolean) => { if (!value && !busy) emit('close') }">
    <div class="w-full max-w-reading p-4">
      <NCard role="dialog" aria-modal="true" aria-labelledby="create-user-title" :closable="!busy" @close="emit('close')">
        <template #header>
          <span id="create-user-title">{{ t('admin.create') }}</span>
        </template>
        <NForm ref="form" :model="model" :rules="rules" label-placement="top" @submit.prevent="submit">
          <NFormItem
            path="username" :label="t('auth.username')" :label-props="{ for: 'admin-username' }"
            :validation-status="fieldError ? 'error' : undefined" :feedback="fieldError || undefined"
          >
            <NInput
              v-model:value="model.username" size="large" :disabled="busy"
              :input-props="{ id: 'admin-username', autocomplete: 'off' }" :placeholder="t('auth.username')"
            />
          </NFormItem>
          <NFormItem :label="t('admin.role')" :label-props="{ for: 'admin-role' }">
            <NSelect
              v-model:value="model.role" size="large" :disabled="busy" :options="roles"
              :input-props="{ 'id': 'admin-role', 'aria-label': t('admin.role') }"
            />
          </NFormItem>
          <div class="flex flex-wrap justify-end gap-3">
            <NButton size="large" :disabled="busy" @click="emit('close')">
              {{ t('common.cancel') }}
            </NButton>
            <NButton size="large" type="primary" attr-type="submit" :loading="busy" :disabled="busy">
              {{ t('admin.create') }}
            </NButton>
          </div>
        </NForm>
      </NCard>
    </div>
  </NModal>
</template>
