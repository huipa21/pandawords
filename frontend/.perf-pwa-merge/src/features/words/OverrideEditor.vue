<script setup lang="ts">
import type { FormInst } from 'naive-ui'
import type { DictionaryRecord, OverrideFields } from './dictionaryView'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { object, text } from './dictionaryView'
import { useWordDrafts } from './useWordDrafts'

const props = defineProps<{ record: DictionaryRecord, busy: boolean, error: string }>()
const emit = defineEmits<{ save: [fields: OverrideFields], cancel: [] }>()
const { t } = useI18n()
const drafts = useWordDrafts()
const form = ref<FormInst>()
const keys = computed(() => props.record.table === 'lemma'
  ? ['text', 'cefr'] as const
  : props.record.table === 'lexeme'
    ? ['etymology_text'] as const
    : ['definition', 'gloss'] as const)
if (!drafts.overrides[props.record.id]) {
  drafts.overrides[props.record.id] = Object.fromEntries(keys.value.map(key => [
    key,
    key === 'gloss'
      ? {
          zh: text(object(props.record.fields.gloss).zh),
        }
      : text(props.record.fields[key]),
  ]))
}
const draft = computed(() => drafts.overrides[props.record.id] ?? {})
const rules = computed(() => Object.fromEntries(keys.value.map(key => [
  key,
  {
    validator: () => {
      const value = key === 'gloss'
        ? draft.value.gloss?.zh
        : draft.value[key]
      return typeof value === 'string' && value.length <= 10000 && (!['text', 'definition'].includes(key) || !!value.trim())
        ? true
        : new Error(t('lemmaDetail.invalidText'))
    },
    trigger: ['input', 'blur'],
  },
])))
function value(key: typeof keys.value[number]) {
  return key === 'gloss'
    ? draft.value.gloss?.zh ?? ''
    : text(draft.value[key])
}
function update(key: typeof keys.value[number], value: string) {
  if (key === 'gloss')
    draft.value.gloss = { zh: value }
  else
    draft.value[key] = value
}
async function save() {
  try {
    await form.value?.validate()
    emit('save', draft.value)
  }
  catch {}
}
function cancel() {
  delete drafts.overrides[props.record.id]
  emit('cancel')
}
</script>

<template>
  <NCard data-testid="word-override-editor" :title="t('lemmaDetail.editOverride')">
    <NForm ref="form" :model="draft" :rules="rules" @submit.prevent="save">
      <NFormItem
        v-for="key in keys" :key="key" :path="key" :label="t(`lemmaDetail.fields.${key}`)"
        :label-props="{ for: `word-override-${key}` }"
        :validation-status="error ? 'error' : undefined" :feedback="error || undefined"
      >
        <NInput
          :value="value(key)" :input-props="{ id: `word-override-${key}` }"
          :type="key === 'text' || key === 'cefr' ? 'text' : 'textarea'"
          :disabled="busy" @update:value="update(key, $event)"
        />
      </NFormItem>
      <div class="flex flex-wrap gap-3">
        <NButton size="large" type="primary" attr-type="submit" data-testid="word-override-save" :loading="busy" :disabled="busy">
          {{ t('word.save') }}
        </NButton>
        <NButton size="large" :disabled="busy" @click="cancel">
          {{ t('word.cancel') }}
        </NButton>
      </div>
    </NForm>
  </NCard>
</template>
