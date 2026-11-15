<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{
  show: boolean
  titleKey: string
  contentKey: string
  params?: Record<string, string>
  loading?: boolean
}>()
const emit = defineEmits<{ confirm: [], cancel: [] }>()
const { t } = useI18n()

function confirm() {
  emit('confirm')
  return false
}
</script>

<template>
  <NModal
    :show="show" preset="dialog" type="warning"
    :style="{ width: 'var(--pw-layout-reading-max-width)', maxWidth: 'calc(100% - var(--pw-space-8))' }"
    :title="t(titleKey)" :content="t(contentKey, params ?? {})"
    :positive-text="t('common.confirm')" :negative-text="t('common.cancel')"
    :positive-button-props="{ size: 'large', loading, disabled: loading }"
    :negative-button-props="{ size: 'large', disabled: loading }"
    :closable="!loading" :mask-closable="!loading" :close-on-esc="!loading"
    @positive-click="confirm" @negative-click="emit('cancel')"
    @update:show="(value: boolean) => { if (!value && !loading) emit('cancel') }"
  />
</template>
