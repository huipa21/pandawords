<script setup lang="ts">
import type { Occurrence } from './readingText'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '@/components/app/PageHeader.vue'
import ReadingLookup from './ReadingLookup.vue'
import { occurrenceState, readingSegments } from './readingText'
import { useReading } from './useReading'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const { reading, passages, projects, moreProjects, loadMoreProjects, loading, failed, unavailable, projectId, passageId, title, source, text, offset, more, load, list, ingest } = useReading()
const selection = ref<{ occurrence: Occurrence, sentenceId: string }>()
const showSelection = ref(false)
const segments = computed(() => reading.value
  ? readingSegments(reading.value)
  : [])
const definition = computed(() => reading.value?.project_senses?.find(sense => sense.id === selection.value?.occurrence.sense_id))
const gloss = computed(() => definition.value?.fields.gloss)
watch(() => route.params.passageId, async (id) => {
  selection.value = undefined
  reading.value = undefined
  showSelection.value = false
  passageId.value = typeof id === 'string'
    ? id
    : ''
  const ready = await list()
  if (passageId.value && ready)
    await load()
}, { immediate: true })
watch(projectId, () => {
  showSelection.value = false
  if (passageId.value)
    void load()
})
async function create() {
  const id = await ingest()
  if (id) {
    await router.push({
      name: 'reading',
      params: { passageId: id },
    })
  }
}
async function retry() {
  const ready = await list()
  if (passageId.value && ready)
    await load()
}
function choose(occurrence: Occurrence, sentenceId: string) {
  selection.value = { occurrence, sentenceId }
  showSelection.value = true
}
async function linked() {
  showSelection.value = false
  await load()
}
</script>

<template>
  <section class="grid min-w-0 gap-4">
    <PageHeader :title="t('reading.title')">
      <template #actions>
        <NButton v-if="passageId" size="large" @click="router.push({ name: 'reading' })">
          {{ t('reading.library') }}
        </NButton>
      </template>
    </PageHeader>
    <label>
      {{ t('reading.project') }}
      <NSelect v-model:value="projectId" clearable :options="projects.map(project => ({ label: project.name, value: project.id }))" :aria-label="t('reading.project')" />
    </label>
    <NButton v-if="moreProjects" size="large" :disabled="loading" @click="loadMoreProjects">
      {{ t('reading.moreProjects') }}
    </NButton>
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="4" />
    </div>
    <div v-if="failed" role="alert" class="grid gap-2">
      <p>{{ t(unavailable ? 'reading.unavailable' : 'reading.failed') }}</p>
      <NButton size="large" @click="retry">
        {{ t('reading.retry') }}
      </NButton>
    </div>
    <template v-if="!passageId">
      <NCard :title="t('reading.create')">
        <form class="grid gap-4" @submit.prevent="create">
          <label>{{ t('reading.passageTitle') }}<NInput v-model:value="title" :maxlength="300" :input-props="{ 'aria-label': t('reading.passageTitle') }" /></label>
          <label>{{ t('reading.source') }}<NInput v-model:value="source" :maxlength="2000" :input-props="{ 'aria-label': t('reading.source') }" /></label>
          <label>{{ t('reading.text') }}<NInput v-model:value="text" type="textarea" :maxlength="20000" :input-props="{ 'aria-label': t('reading.text') }" /></label>
          <NButton size="large" type="primary" attr-type="submit" :disabled="loading || !text.trim()" :loading="loading">
            {{ t('reading.ingest') }}
          </NButton>
        </form>
      </NCard>
      <p v-if="!loading && !passages.length">
        {{ t('reading.empty') }}
      </p>
      <ul class="grid list-none gap-2 p-0">
        <li v-for="passage in passages" :key="passage.id">
          <NButton size="large" @click="router.push({ name: 'reading', params: { passageId: passage.id } })">
            {{ passage.title || passage.text.slice(0, 60) }}
          </NButton>
        </li>
      </ul>
      <div class="flex flex-wrap gap-2">
        <NButton size="large" :disabled="loading || offset === 0" @click="offset -= 50; list()">
          {{ t('reading.previous') }}
        </NButton>
        <NButton size="large" :disabled="loading || !more" @click="offset += 50; list()">
          {{ t('reading.next') }}
        </NButton>
      </div>
    </template>
    <template v-if="reading">
      <h2 class="break-words text-xl">
        {{ reading.passage.title }}
      </h2>
      <p v-if="reading.passage.source" class="break-words text-muted">
        {{ t('reading.source') }}: {{ reading.passage.source }}
      </p>
      <p class="text-sm">
        {{ t('reading.legend') }}
      </p>
      <article class="reading-body whitespace-pre-wrap break-words leading-relaxed" :aria-label="t('reading.text')">
        <template v-for="(segment, index) in segments" :key="index">
          <button
            v-if="segment.occurrence && segment.sentenceId"
            class="reading-word rounded-sm border-0 focus-visible:pw-focus-ring"
            :class="{
              'bg-primary-soft text-primary': occurrenceState(reading, segment.occurrence) === 'selected',
              'bg-page text-fg underline decoration-dotted': occurrenceState(reading, segment.occurrence) === 'outside',
              'bg-page text-fg': occurrenceState(reading, segment.occurrence) === 'unlinked',
            }"
            :data-state="occurrenceState(reading, segment.occurrence)"
            :aria-label="`${segment.text}: ${t(`reading.${occurrenceState(reading, segment.occurrence)}`)}`"
            @click="choose(segment.occurrence, segment.sentenceId)"
          >
            {{ segment.text }}
          </button><template v-else>
            {{ segment.text }}
          </template>
        </template>
      </article>
    </template>
    <NCard v-if="selection" v-show="showSelection" :title="selection.occurrence.text" role="region" :aria-label="t('reading.selection')">
      <div v-if="definition" class="grid gap-2">
        <p>{{ definition.fields.definition }}</p>
        <template v-if="gloss && typeof gloss === 'object' && !Array.isArray(gloss)">
          <p v-for="(value, lang) in gloss" :key="lang">
            {{ lang }}: {{ value }}
          </p>
        </template>
      </div>
      <p v-else>
        {{ t(selection.occurrence.sense_id ? 'reading.outside' : 'reading.unlinked') }}
      </p>
      <ReadingLookup :occurrence="selection.occurrence" :sentence-id="selection.sentenceId" :project-id="projectId" @dismiss="showSelection = false" @linked="linked" />
    </NCard>
  </section>
</template>

<style scoped>
.reading-word {
  min-height: var(--pw-layout-touch-target);
  min-width: var(--pw-layout-touch-target);
  padding: 0;
  cursor: pointer;
  font: inherit;
}
</style>
