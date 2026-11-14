<script setup lang="ts">
import { useId } from 'vue'
import { useI18n } from 'vue-i18n'

withDefaults(defineProps<{
  target: string
  kind?: 'note' | 'mnemonic'
  modelValue?: string
  saving?: boolean
  disabled?: boolean
}>(), { kind: 'note', modelValue: '' })
const emit = defineEmits<{
  'update:modelValue': [value: string]
  'save': [value: { target: string, kind: 'note' | 'mnemonic', text: string }]
  'cancel': []
}>()
const id = useId()
const { t } = useI18n()
</script>

<template>
  <NForm @submit.prevent="!disabled && !saving && emit('save', { target, kind, text: modelValue })">
    <NFormItem :label="t(`word.${kind}`)" :label-props="{ for: id }">
      <NInput
        :value="modelValue" type="textarea" :input-props="{ id }" :disabled="disabled || saving"
        :placeholder="t('word.notePlaceholder')" @update:value="emit('update:modelValue', $event)"
      />
    </NFormItem>
    <div class="flex flex-wrap gap-3">
      <NButton size="large" type="primary" attr-type="submit" :loading="saving" :disabled="disabled || saving">
        {{ t('word.save') }}
      </NButton>
      <NButton size="large" :disabled="disabled || saving" @click="emit('cancel')">
        {{ t('word.cancel') }}
      </NButton>
    </div>
  </NForm>
</template>
