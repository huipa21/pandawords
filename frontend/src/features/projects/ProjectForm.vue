<script setup lang="ts">
import type { FormInst } from 'naive-ui'
import type { ProjectCreate } from './useProject'
import { computed, reactive, ref, useTemplateRef } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  initial?: ProjectCreate
  busy: boolean
  fields: Record<string, string>
  save: (body: ProjectCreate) => Promise<void>
}>()
const emit = defineEmits<{ cancel: [] }>()
const { t } = useI18n()
const form = useTemplateRef<FormInst>('form')
const dailyNew = ref<number | null>(props.initial?.plan?.daily_new ?? 20)
const model = reactive({
  name: props.initial?.name ?? '',
  description: props.initial?.description ?? '',
  target_lang: props.initial?.target_lang ?? 'en',
  source_lang: props.initial?.source_lang ?? 'zh',
  plan: {
    ...props.initial?.plan,
    daily_new: dailyNew,
    review_cap: props.initial?.plan?.review_cap ?? null,
    exam_date: props.initial?.plan?.exam_date ?? null,
  },
})
const examDate = computed<number | null>({
  get: () => model.plan.exam_date
    ? Date.parse(model.plan.exam_date)
    : null,
  set: (value) => {
    model.plan.exam_date = value === null
      ? null
      : new Date(value).toISOString()
  },
})
const rules = computed(() => {
  const text = (max: number, required = true) => ({
    validator: (_rule: unknown, value: string) => (!required || !!value.trim()) && value.trim().length <= max,
    message: t('projects.textValidation', { max }),
    trigger: ['blur', 'input'],
  })
  const integer = (nullable: boolean) => ({
    validator: (_rule: unknown, value: number | null) => (nullable && value === null) || (Number.isSafeInteger(value) && value !== null && value >= 0),
    message: t('projects.numberValidation'),
    trigger: ['blur', 'change'],
  })
  return {
    'name': text(128),
    'description': {
      validator: (_rule: unknown, value: string) => value.length <= 10000,
      message: t('projects.descriptionValidation'),
      trigger: ['blur', 'input'],
    },
    'target_lang': text(35),
    'source_lang': text(35),
    'plan.daily_new': integer(false),
    'plan.review_cap': integer(true),
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
  if (model.plan.daily_new === null)
    return
  await props.save({
    ...model,
    name: model.name.trim(),
    target_lang: model.target_lang.trim(),
    source_lang: model.source_lang.trim(),
    plan: { ...model.plan, daily_new: model.plan.daily_new },
  })
}
</script>

<template>
  <NForm ref="form" :model="model" :rules="rules" label-placement="top" data-testid="project-form" @submit.prevent="submit">
    <NFormItem
      v-for="field in (['name', 'description', 'target_lang', 'source_lang'] as const)" :key="field"
      :path="field" :label="t(`projects.fields.${field}`)" :label-props="{ for: `project-${field}` }"
      :validation-status="fields[field] ? 'error' : undefined" :feedback="fields[field]"
    >
      <NInput
        v-model:value="model[field]" size="large" :type="field === 'description' ? 'textarea' : 'text'"
        :disabled="busy" :input-props="{ id: `project-${field}` }" :placeholder="t(`projects.fields.${field}`)"
      />
    </NFormItem>
    <NFormItem
      path="plan.daily_new" :label="t('projects.fields.daily_new')" :label-props="{ for: 'project-daily-new' }"
      :validation-status="fields['plan.daily_new'] ? 'error' : undefined" :feedback="fields['plan.daily_new']"
    >
      <NInputNumber v-model:value="dailyNew" class="w-full" size="large" :disabled="busy" :show-button="false" :input-props="{ id: 'project-daily-new' }" />
    </NFormItem>
    <NFormItem
      path="plan.review_cap" :label="t('projects.fields.review_cap')" :label-props="{ for: 'project-review-cap' }"
      :validation-status="fields['plan.review_cap'] ? 'error' : undefined" :feedback="fields['plan.review_cap']"
    >
      <NInputNumber v-model:value="model.plan.review_cap" class="w-full" size="large" clearable :disabled="busy" :show-button="false" :input-props="{ id: 'project-review-cap' }" :placeholder="t('projects.unlimited')" />
    </NFormItem>
    <NFormItem
      path="plan.exam_date" :show-label="false"
      :validation-status="fields['plan.exam_date'] ? 'error' : undefined" :feedback="fields['plan.exam_date']"
    >
      <label id="project-exam-date" class="block w-full">
        <span class="mb-2 block">{{ t('projects.fields.exam_date') }}</span>
        <NDatePicker v-model:value="examDate" class="w-full" size="large" type="date" clearable :disabled="busy" :placeholder="t('projects.noExamDate')" />
      </label>
    </NFormItem>
    <p class="text-muted">
      {{ t('projects.planNotice') }}
    </p>
    <div class="flex flex-wrap justify-end gap-3">
      <NButton size="large" :disabled="busy" @click="emit('cancel')">
        {{ t('common.cancel') }}
      </NButton>
      <NButton size="large" type="primary" attr-type="submit" :loading="busy" :disabled="busy" data-testid="project-save">
        {{ t('projects.save') }}
      </NButton>
    </div>
  </NForm>
</template>
