<script setup lang="ts">
import type { components } from '@/api/schema'
import { useI18n } from 'vue-i18n'
import JobStatus from '@/components/app/JobStatus.vue'
import SenseSelectList from '@/components/word/SenseSelectList.vue'
import WordHeader from '@/components/word/WordHeader.vue'
import { useAddWord } from './useAddWord'

const props = defineProps<{ projectId: string, show: boolean }>()
const emit = defineEmits<{
  'update:show': [show: boolean]
  'added': [result: components['schemas']['AddToProjectRead']]
  'jobsSettled': [jobs: components['schemas']['JobRead'][]]
}>()
const { t } = useI18n()
const {
  text,
  candidates,
  candidateIndex,
  selected,
  view,
  selectedSenses,
  searching,
  submitting,
  searched,
  busy,
  error,
  added,
  jobs,
  choose,
  search,
  submit,
} = useAddWord(() => props.projectId, () => props.show)

async function add() {
  const result = await submit()
  if (result)
    emit('added', result)
}
</script>

<template>
  <NModal
    :show="show" preset="card" :title="t('addWord.title')" :bordered="false"
    class="overflow-y-auto"
    :style="{ width: 'var(--pw-layout-reading-max-width)', maxWidth: 'calc(100% - var(--pw-space-4))', maxHeight: 'calc(100dvh - var(--pw-space-4))' }"
    :aria-label="t('addWord.title')" data-testid="add-word-dialog"
    @update:show="emit('update:show', $event)" @close="emit('update:show', false)"
  >
    <div class="space-y-6">
      <form class="space-y-3" @submit.prevent="search">
        <label for="add-word-input" class="block font-medium">{{ t('addWord.input') }}</label>
        <NInput
          v-model:value="text" size="large" :disabled="busy"
          :placeholder="t('addWord.placeholder')" :input-props="{ 'id': 'add-word-input', 'data-testid': 'add-word-input' }"
        />
        <NButton attr-type="submit" size="large" type="primary" :loading="searching" :disabled="busy || !text.trim()" data-testid="add-word-search">
          {{ t('addWord.search') }}
        </NButton>
      </form>
      <p v-if="searching" role="status" class="text-muted">
        {{ t('common.loading') }}
      </p>
      <p v-if="error" role="alert" class="text-error" data-testid="add-word-error">
        {{ error }}
      </p>
      <p v-if="searched && !candidates.length" role="status" class="text-muted">
        {{ t('addWord.noMatches') }}
      </p>
      <template v-if="view">
        <div v-if="candidates.length > 1" role="group" :aria-label="t('addWord.candidates')" class="flex flex-wrap gap-2">
          <NButton
            v-for="(item, index) in candidates" :key="JSON.stringify(item.lemma.id)"
            size="large" :disabled="busy" :aria-pressed="candidateIndex === index"
            :type="candidateIndex === index ? 'primary' : 'default'"
            data-testid="add-word-candidate" @click="choose(index)"
          >
            {{ item.lemma.text }}
          </NButton>
        </div>
        <WordHeader :lemma="view.lemma" />
        <fieldset :disabled="busy" :inert="busy" class="m-0 min-w-0 border-0 p-0">
          <legend class="mb-3 font-medium">
            {{ t('word.selectSenses') }}
          </legend>
          <SenseSelectList :key="view.lemma.id" v-model:selected="selected" :candidates="view.lexemes" />
        </fieldset>
        <NButton size="large" type="primary" :loading="submitting" :disabled="busy || !selectedSenses.length" data-testid="add-word-submit" @click="add">
          {{ t('addWord.submit') }}
        </NButton>
      </template>
      <p v-if="added" role="status" class="text-success" data-testid="add-word-success">
        {{ t('addWord.added') }}
      </p>
      <JobStatus v-model:jobs="jobs" :active="show" @settled="emit('jobsSettled', $event)" />
      <NButton size="large" data-testid="add-word-close" @click="emit('update:show', false)">
        {{ t('addWord.close') }}
      </NButton>
    </div>
  </NModal>
</template>
