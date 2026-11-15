<script setup lang="ts">
import type { DictionaryRecord } from './dictionaryView'
import type { components } from '@/api/schema'
import { useMessage } from 'naive-ui'
import { computed, onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import NoteEditor from '@/components/word/NoteEditor.vue'
import { useAuthStore } from '@/stores/auth'
import MnemonicSuggestion from './MnemonicSuggestion.vue'
import { useWordErrors } from './useLemmaDetail'
import { useWordDrafts } from './useWordDrafts'

const props = defineProps<{ target: DictionaryRecord }>()
const { t } = useI18n()
const message = useMessage()
const errorText = useWordErrors()
const drafts = useWordDrafts()
const auth = useAuthStore()
const kind = ref<'note' | 'mnemonic'>('note')
const notes = ref<components['schemas']['NoteRead'][]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const editing = ref<components['schemas']['NoteRead']>()
const removing = ref<components['schemas']['NoteRead']>()
const currentKind = computed(() => editing.value?.kind ?? kind.value)
const key = computed(() => editing.value?.id ?? (kind.value === 'note'
  ? `new:${props.target.id}`
  : `new:mnemonic:${props.target.id}`))
const draft = computed({
  get: () => drafts.notes[key.value] ?? '',
  set: value => drafts.notes[key.value] = value,
})
let disposed = false
let version = 0
onScopeDispose(() => {
  disposed = true
  version++
})
watch(() => [props.target.id, props.target.table, auth.user?.id], () => {
  version++
  editing.value = undefined
  removing.value = undefined
  notes.value = []
  busy.value = false
  void load()
}, { flush: 'sync' })

async function load() {
  const started = version
  loading.value = true
  error.value = ''
  try {
    const result = await api.GET('/api/notes', {
      params: {
        query: { target_table: props.target.table, target_id: props.target.id },
      },
    })
    if (disposed || started !== version)
      return
    if (result.data)
      notes.value = result.data
    else
      error.value = errorText(result.error, result.response.status)
  }
  catch {
    if (!disposed && started === version)
      error.value = t('errors.transport')
  }
  finally {
    if (!disposed && started === version)
      loading.value = false
  }
}
function edit(note: components['schemas']['NoteRead']) {
  editing.value = note
  drafts.notes[note.id] ??= note.text
}
function cancel() {
  delete drafts.notes[key.value]
  editing.value = undefined
}
async function save() {
  if (busy.value)
    return
  if (!draft.value.trim() || draft.value.length > 10000) {
    message.error(t('lemmaDetail.invalidNote'))
    return
  }
  busy.value = true
  const started = version
  const draftKey = key.value
  try {
    const result = editing.value
      ? await api.PATCH('/api/notes/{id}', {
          params: {
            path: { id: editing.value.id },
          },
          body: { text: draft.value },
        })
      : await api.POST('/api/notes', {
          body: {
            target_table: props.target.table,
            target_id: props.target.id,
            kind: currentKind.value,
            text: draft.value,
          },
        })
    if (disposed || started !== version)
      return
    if (result.data) {
      const saved = result.data
      notes.value = [
        ...notes.value.filter(note => note.id !== saved.id),
        saved,
      ]
      delete drafts.notes[draftKey]
      editing.value = undefined
      message.success(t('lemmaDetail.saved'), { duration: 2000 })
    }
    else {
      message.error(errorText(result.error, result.response.status))
    }
  }
  catch {
    if (!disposed && started === version)
      message.error(t('errors.transport'))
  }
  finally {
    if (started === version)
      busy.value = false
  }
}
async function remove() {
  const note = removing.value
  if (!note || busy.value)
    return
  busy.value = true
  const started = version
  try {
    const result = await api.DELETE('/api/notes/{id}', {
      params: {
        path: { id: note.id },
      },
    })
    if (disposed || started !== version)
      return
    if (result.response.ok) {
      notes.value = notes.value.filter(item => item.id !== note.id)
      if (editing.value?.id === note.id)
        cancel()
      delete drafts.notes[note.id]
      removing.value = undefined
      message.success(t('lemmaDetail.saved'), { duration: 2000 })
    }
    else {
      message.error(errorText(result.error, result.response.status))
    }
  }
  catch {
    if (!disposed && started === version)
      message.error(t('errors.transport'))
  }
  finally {
    if (started === version)
      busy.value = false
  }
}
void load()
</script>

<template>
  <NCard :title="t('lemmaDetail.notes')" data-testid="word-notes" :data-target-id="target.id">
    <div class="space-y-4">
      <NButton size="large" :disabled="busy || loading" @click="load">
        {{ t('lemmaDetail.refresh') }}
      </NButton>
      <NSkeleton v-if="loading && !notes.length" text :repeat="2" />
      <ErrorState v-if="error" :error="error" @retry="load" />
      <EmptyState v-else-if="!loading && !notes.length" title-key="lemmaDetail.emptyNotes" />
      <article v-for="note in notes" :key="note.id" class="space-y-2" data-testid="word-note" :data-note-id="note.id">
        <NTag>{{ t(`word.${note.kind}`) }}</NTag>
        <p class="whitespace-pre-wrap break-words">
          {{ note.text }}
        </p>
        <div class="flex flex-wrap gap-3">
          <NButton size="large" :disabled="busy" data-testid="word-note-edit" @click="edit(note)">
            {{ t('word.edit') }}
          </NButton>
          <NButton size="large" :disabled="busy" data-testid="word-note-delete" @click="removing = note">
            {{ t('lemmaDetail.deleteNote') }}
          </NButton>
        </div>
      </article>
      <div data-testid="word-note-editor">
        <div v-if="!editing" class="mb-3 flex flex-wrap gap-3">
          <NButton v-for="option in (['note', 'mnemonic'] as const)" :key="option" size="large" :aria-pressed="kind === option" :disabled="busy" :data-testid="`word-kind-${option}`" @click="kind = option">
            {{ t(`word.${option}`) }}
          </NButton>
        </div>
        <NoteEditor v-model="draft" :target="target.id" :kind="currentKind" :saving="busy" @save="save" @cancel="cancel" />
        <MnemonicSuggestion v-if="currentKind === 'mnemonic'" :target="target" :draft="draft" :disabled="busy" @accept="draft = $event" />
      </div>
    </div>
    <ConfirmAction
      :show="!!removing" title-key="lemmaDetail.deleteNote" content-key="lemmaDetail.deleteNoteConfirm"
      :loading="busy" @confirm="remove" @cancel="removing = undefined"
    />
  </NCard>
</template>
