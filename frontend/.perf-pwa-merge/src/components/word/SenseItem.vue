<script setup lang="ts">
import type { SenseView } from './types'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = withDefaults(defineProps<{
  sense: SenseView
  selectable?: boolean
  selected?: boolean
  hidden?: boolean
  editable?: boolean
}>(), { hidden: undefined })
const emit = defineEmits<{
  'update:selected': [value: boolean]
  'edit': [id: string]
  'hide': [id: string, hidden: boolean]
  'note': [id: string]
}>()
const { t } = useI18n()
const expanded = ref(false)
</script>

<template>
  <article
    class="min-w-0 space-y-2 border border-base rounded-md p-3"
    :class="{ 'bg-surface text-muted': hidden ?? sense.hidden }"
    :data-hidden="hidden ?? sense.hidden ?? false"
  >
    <NCheckbox
      v-if="selectable" class="min-h-12 w-full"
      :checked="selected ?? false" :disabled="hidden ?? sense.hidden"
      :aria-disabled="hidden ?? sense.hidden ?? false"
      :aria-label="sense.definition" @update:checked="emit('update:selected', $event)"
    >
      <span lang="en" class="block break-words whitespace-normal">{{ sense.definition }}</span>
    </NCheckbox>
    <p v-else lang="en" class="m-0 break-words">
      {{ sense.definition }}
    </p>
    <p v-if="sense.gloss" lang="zh-CN" class="m-0 break-words text-muted">
      {{ sense.gloss }}
    </p>
    <div class="flex flex-wrap gap-2">
      <NTag v-if="sense.common">
        {{ t('word.common') }}
      </NTag>
      <NTag v-if="hidden ?? sense.hidden">
        {{ t('word.hidden') }}
      </NTag>
      <NTag v-if="sense.overridden" type="info">
        {{ t('word.overridden') }}
      </NTag>
      <NTag v-if="sense.register">
        {{ sense.register }}
      </NTag>
      <NTag v-if="sense.domain">
        {{ sense.domain }}
      </NTag>
    </div>
    <div class="flex flex-wrap gap-2">
      <NButton v-if="sense.examples?.length" size="large" :aria-expanded="expanded" @click="expanded = !expanded">
        {{ t(expanded ? 'word.collapseExamples' : 'word.examples') }}
      </NButton>
      <template v-if="editable">
        <NButton size="large" @click="emit('edit', props.sense.id)">
          {{ t('word.edit') }}
        </NButton>
        <NButton size="large" @click="emit('hide', props.sense.id, !(hidden ?? sense.hidden))">
          {{ t((hidden ?? sense.hidden) ? 'word.unhide' : 'word.hide') }}
        </NButton>
        <NButton size="large" @click="emit('note', props.sense.id)">
          {{ t('word.note') }}
        </NButton>
      </template>
    </div>
    <ul v-if="expanded" class="m-0 space-y-2 ps-4">
      <li v-for="(example, index) in sense.examples" :key="index">
        <p lang="en" class="m-0 break-words">
          {{ example.text }}
        </p>
        <p v-if="example.translation" lang="zh-CN" class="m-0 break-words text-muted">
          {{ example.translation }}
        </p>
      </li>
    </ul>
  </article>
</template>
