<script setup lang="ts">
import type { NodeType, RelationType } from '@/components/word/types'
import { useMessage } from 'naive-ui'
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AudioButton from '@/components/word/AudioButton.vue'
import LemmaTree from '@/components/word/LemmaTree.vue'
import LexemeBlock from '@/components/word/LexemeBlock.vue'
import NodeTypeBadge from '@/components/word/NodeTypeBadge.vue'
import NoteEditor from '@/components/word/NoteEditor.vue'
import PronunciationChip from '@/components/word/PronunciationChip.vue'
import RelationBadge from '@/components/word/RelationBadge.vue'
import SenseSelectList from '@/components/word/SenseSelectList.vue'
import WordHeader from '@/components/word/WordHeader.vue'
import { graphEdges, graphNodes } from '@/design/tokens'
import { previewAudioSource, wordSamples } from './wordSamples'

const { t } = useI18n()
const message = useMessage()
const items = ref(structuredClone(wordSamples))
const candidates = computed(() => items.value.flatMap(item => item.lexemes))
const selected = ref<string[]>()
const expanded = ref(['bank', 'bank-noun'])
const treeSelected = ref<string[]>([])
const note = ref('')
const nodes = Object.keys(graphNodes) as NodeType[]
const relations = Object.keys(graphEdges) as RelationType[]
const src = previewAudioSource()
onBeforeUnmount(() => URL.revokeObjectURL(src))
function action(key: 'edit' | 'note' | 'audio') {
  message.info(t('word.preview.action', {
    action: t(key === 'audio'
      ? 'word.audio.play'
      : `word.${key}`),
  }))
}
function hide(id: string, hidden: boolean) {
  const sense = candidates.value.flatMap(lexeme => lexeme.senses).find(sense => sense.id === id)
  if (sense)
    sense.hidden = hidden
}
</script>

<template>
  <section class="min-w-0 space-y-4">
    <h3 class="text-xl font-semibold">
      {{ t('word.preview.title') }}
    </h3>
    <div class="flex flex-wrap gap-2">
      <NodeTypeBadge v-for="node in nodes" :key="node" :type="node" />
      <RelationBadge v-for="relation in relations" :key="relation" :type="relation" />
    </div>
    <div v-for="item in items" :key="item.lemma.id" class="min-w-0 space-y-4">
      <WordHeader :lemma="{ ...item.lemma, frequencyBand: t('word.preview.frequency') }" size="xl" />
      <LexemeBlock
        v-for="lexeme in item.lexemes" :key="lexeme.id" :lexeme="lexeme" editable
        @hide="hide" @edit="action('edit')" @note="action('note')" @play="action('audio')"
      />
    </div>
    <h4 class="text-lg font-semibold">
      {{ t('word.preview.audio') }}
    </h4>
    <div class="flex flex-wrap items-center gap-3">
      <AudioButton :src="src" />
      <AudioButton @play="action('audio')" />
      <PronunciationChip ipa="bæŋk" accent="UK" disabled />
    </div>
    <h4 class="text-lg font-semibold">
      {{ t('word.preview.selection') }}
    </h4>
    <SenseSelectList v-model:selected="selected" :candidates="candidates" />
    <h4 class="text-lg font-semibold">
      {{ t('word.preview.tree') }}
    </h4>
    <LemmaTree
      v-model:expanded-keys="expanded" v-model:selected-keys="treeSelected" :items="items" editable
      @hide="hide" @edit="action('edit')" @note="action('note')" @play="action('audio')"
    />
    <NoteEditor
      v-model="note" target="bank-money"
      @save="message.success(t('word.preview.saved'))" @cancel="note = ''"
    />
    <NoteEditor target="bank-river" kind="mnemonic" :model-value="t('word.preview.note')" disabled />
    <h4 class="text-lg font-semibold">
      {{ t('word.preview.empty') }}
    </h4>
    <SenseSelectList :candidates="[]" />
    <LemmaTree :items="[]" />
  </section>
</template>
