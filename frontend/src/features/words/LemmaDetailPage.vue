<script setup lang="ts">
import type { DictionaryRecord, OverrideFields } from './dictionaryView'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import PosBadge from '@/components/word/PosBadge.vue'
import PronunciationChip from '@/components/word/PronunciationChip.vue'
import SenseItem from '@/components/word/SenseItem.vue'
import WordHeader from '@/components/word/WordHeader.vue'
import TagAssignments from '@/features/tags/TagAssignments.vue'
import { entryRecords, lemmaView, posView, pronunciations, senseView, text } from './dictionaryView'
import LemmaNotes from './LemmaNotes.vue'
import OverrideEditor from './OverrideEditor.vue'
import { useLemmaDetail } from './useLemmaDetail'
import { usePronunciation } from './usePronunciation'
import { useWordDrafts } from './useWordDrafts'

const { t } = useI18n()
const route = useRoute()
const id = () => String(route.params.lemmaId)
const { entry, overrides, loading, busy, loadError, fieldError, load, mutate } = useLemmaDetail(id)
const playback = usePronunciation(id)
const drafts = useWordDrafts()
const editing = ref<DictionaryRecord>()
const resetting = ref<DictionaryRecord>()
const noteTarget = ref<string>()
const tagTarget = ref<string>()
const records = computed(() => entry.value
  ? entryRecords(entry.value)
  : [])
const noteRecord = computed(() => records.value.find(record => record.id === noteTarget.value) ?? entry.value?.lemma)
const noteOptions = computed(() => records.value.map(record => ({
  value: record.id,
  label: `${t(`word.node.${record.table}`)}: ${text(record.fields.text) || text(record.fields.definition) || text(record.fields.pos)}`,
})))
watch(id, () => {
  editing.value = undefined
  resetting.value = undefined
  noteTarget.value = undefined
  tagTarget.value = undefined
})
function edit(record: DictionaryRecord) {
  fieldError.value = ''
  editing.value = record
}
async function save(fields: OverrideFields) {
  const record = editing.value
  if (record && await mutate(record, fields)) {
    delete drafts.overrides[record.id]
    editing.value = undefined
  }
}
async function reset() {
  const record = resetting.value
  if (record && await mutate(record)) {
    delete drafts.overrides[record.id]
    if (editing.value?.id === record.id)
      editing.value = undefined
    resetting.value = undefined
  }
}
</script>

<template>
  <section class="grid gap-6" data-testid="word-detail">
    <PageHeader :title="entry ? text(entry.lemma.fields.text) : t('pages.word')">
      <template #actions>
        <NSpin v-if="loading && entry" size="small" />
        <NButton size="large" :disabled="loading || busy" data-testid="word-refresh" @click="load">
          {{ t('lemmaDetail.refresh') }}
        </NButton>
      </template>
    </PageHeader>
    <div v-if="loading && !entry" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="5" />
    </div>
    <ErrorState v-if="loadError" :error="loadError" :loading="loading" @retry="load" />
    <template v-if="entry">
      <NCard>
        <WordHeader :lemma="lemmaView(entry.lemma)" size="xl" />
        <NTag v-if="text(entry.lemma.fields.cefr)" class="mt-3">
          {{ t('lemmaDetail.cefr', { level: text(entry.lemma.fields.cefr) }) }}
        </NTag>
        <div class="mt-4 flex flex-wrap gap-3">
          <NButton size="large" :disabled="busy" data-testid="word-lemma-edit" @click="edit(entry.lemma)">
            {{ t('lemmaDetail.editOverride') }}
          </NButton>
          <NButton v-if="overrides[entry.lemma.id]" size="large" :disabled="busy" data-testid="word-lemma-reset" @click="resetting = entry.lemma">
            {{ t('lemmaDetail.resetOverride') }}
          </NButton>
        </div>
      </NCard>
      <EmptyState v-if="!entry.lexemes.length" title-key="lemmaDetail.emptySenses" />
      <NCard v-for="item in entry.lexemes" :key="item.lexeme.id" data-testid="word-lexeme" :data-lexeme-id="item.lexeme.id">
        <div class="space-y-4">
          <div class="flex flex-wrap items-center gap-3">
            <PosBadge :pos="posView(item.lexeme.fields.pos)" />
            <PronunciationChip
              v-for="pron in pronunciations(item.lexeme)" :key="pron.id" :ipa="pron.ipa" :accent="pron.accent"
              data-testid="word-pronunciation" :data-media-id="pron.mediaId"
              :playback-state="playback.current.value === pron.id && (playback.loading.value || playback.playing.value) ? 'playing' : 'stopped'"
              @play="playback.play(pron.mediaId, pron.id)"
            />
            <NSpin v-if="playback.loading.value" size="small" />
          </div>
          <p v-if="!pronunciations(item.lexeme).some(pron => pron.mediaId)" class="text-muted" data-testid="word-missing-audio">
            {{ t('lemmaDetail.missingAudio') }}
          </p>
          <p v-if="text(item.lexeme.fields.etymology_text)" class="whitespace-pre-wrap break-words">
            {{ text(item.lexeme.fields.etymology_text) }}
          </p>
          <div class="flex flex-wrap gap-3">
            <NButton size="large" :disabled="busy" data-testid="word-lexeme-edit" @click="edit(item.lexeme)">
              {{ t('lemmaDetail.editOverride') }}
            </NButton>
            <NButton v-if="overrides[item.lexeme.id]" size="large" :disabled="busy" data-testid="word-lexeme-reset" @click="resetting = item.lexeme">
              {{ t('lemmaDetail.resetOverride') }}
            </NButton>
          </div>
          <EmptyState v-if="!item.senses.length" title-key="lemmaDetail.emptySenses" />
          <div v-for="sense in item.senses" :key="sense.id" class="space-y-3" data-testid="word-sense" :data-sense-id="sense.id">
            <SenseItem :sense="senseView(sense, !!overrides[sense.id])" />
            <div class="flex flex-wrap gap-3">
              <NButton size="large" :disabled="busy" data-testid="word-sense-edit" @click="edit(sense)">
                {{ t('word.edit') }}
              </NButton>
              <NButton v-if="overrides[sense.id]" size="large" :disabled="busy" data-testid="word-sense-reset" @click="resetting = sense">
                {{ t('lemmaDetail.resetOverride') }}
              </NButton>
              <NButton size="large" :disabled="busy" data-testid="word-sense-note" @click="noteTarget = sense.id">
                {{ t('word.note') }}
              </NButton>
              <NButton size="large" :disabled="busy" data-testid="word-sense-tags" @click="tagTarget = tagTarget === sense.id ? undefined : sense.id">
                {{ t('tags.title') }}
              </NButton>
            </div>
            <TagAssignments v-if="tagTarget === sense.id" :key="sense.id" :target="{ target_table: 'sense', target_id: sense.id }" />
          </div>
        </div>
      </NCard>
      <OverrideEditor
        v-if="editing" :key="editing.id" :record="editing" :busy="busy" :error="fieldError"
        @save="save" @cancel="editing = undefined"
      />
      <NFormItem v-if="!editing" :label="t('lemmaDetail.noteTarget')" :label-props="{ for: 'word-note-target' }">
        <NSelect
          v-model:value="noteTarget" :options="noteOptions" :placeholder="noteOptions[0]?.label"
          :input-props="{ id: 'word-note-target' }"
        />
      </NFormItem>
      <LemmaNotes v-if="noteRecord && !editing" :key="noteRecord.id" :target="noteRecord" />
    </template>
    <ConfirmAction
      :show="!!resetting" title-key="lemmaDetail.resetOverride" content-key="lemmaDetail.resetConfirm"
      :loading="busy" @confirm="reset" @cancel="resetting = undefined"
    />
  </section>
</template>
