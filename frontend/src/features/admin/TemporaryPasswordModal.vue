<script setup lang="ts">
import { useMessage } from 'naive-ui'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ password: string, username: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const message = useMessage()
const copying = ref(false)

async function copy() {
  copying.value = true
  try {
    await navigator.clipboard.writeText(props.password)
    message.success(t('admin.copied'))
  }
  catch {
    message.error(t('admin.copyFailed'))
  }
  finally {
    copying.value = false
  }
}
</script>

<template>
  <NModal :show="Boolean(password)" @update:show="(value: boolean) => { if (!value) emit('close') }">
    <div class="w-full max-w-reading p-4">
      <NCard role="dialog" aria-modal="true" aria-labelledby="temporary-password-title" closable @close="emit('close')">
        <template #header>
          <span id="temporary-password-title">{{ t('admin.temporaryPassword') }}</span>
        </template>
        <p class="break-words">
          {{ t('admin.passwordNotice', { username }) }}
        </p>
        <output class="block select-text break-all rounded-md bg-surface p-4 font-mono" :aria-label="t('admin.temporaryPassword')">{{ password }}</output>
        <div class="mt-4 flex flex-wrap justify-end gap-3">
          <NButton size="large" :loading="copying" :disabled="copying" @click="copy">
            {{ t('admin.copy') }}
          </NButton>
          <NButton size="large" type="primary" @click="emit('close')">
            {{ t('common.done') }}
          </NButton>
        </div>
      </NCard>
    </div>
  </NModal>
</template>
