<script setup lang="ts">
import type { TreeOption } from 'naive-ui'
import type { LemmaBranch, LexemeView, Pronunciation, SenseView } from './types'
import { computed, h } from 'vue'
import { useI18n } from 'vue-i18n'
import LexemeBlock from './LexemeBlock.vue'
import SenseItem from './SenseItem.vue'
import WordHeader from './WordHeader.vue'

const props = defineProps<{
  items: LemmaBranch[]
  expandedKeys?: string[]
  selectedKeys?: string[]
  editable?: boolean
}>()
const emit = defineEmits<{
  'update:expandedKeys': [keys: string[]]
  'update:selectedKeys': [keys: string[]]
  'edit': [id: string]
  'hide': [id: string, hidden: boolean]
  'note': [id: string]
  'play': [pronunciation: Pronunciation]
}>()
const { t } = useI18n()
interface WordTreeOption extends TreeOption {
  lemma?: LemmaBranch['lemma']
  lexeme?: LexemeView
  sense?: SenseView
}
const data = computed<WordTreeOption[]>(() => props.items.map(({ lemma, lexemes }) => ({
  key: lemma.id,
  label: lemma.text,
  lemma,
  children: lexemes.map(lexeme => ({
    key: lexeme.id,
    label: t(`word.pos.${lexeme.pos}`),
    lexeme,
    children: lexeme.senses.map(sense => ({ key: sense.id, label: sense.definition, sense })),
  })),
})))
function renderLabel({ option }: { option: TreeOption }) {
  const node = option as WordTreeOption
  if (node.lemma)
    return h(WordHeader, { lemma: node.lemma, size: 'md' })
  if (node.lexeme) {
    return h(LexemeBlock, {
      lexeme: { ...node.lexeme, senses: [] },
      onPlay: pronunciation => emit('play', pronunciation),
      onClick: (event: MouseEvent) => {
        if ((event.target as HTMLElement).closest('button'))
          event.stopPropagation()
      },
    })
  }
  return h(SenseItem, {
    sense: node.sense!,
    editable: props.editable,
    onEdit: id => emit('edit', id),
    onHide: (id, hidden) => emit('hide', id, hidden),
    onNote: id => emit('note', id),
    onClick: (event: MouseEvent) => {
      if ((event.target as HTMLElement).closest('button'))
        event.stopPropagation()
    },
  })
}
</script>

<template>
  <div class="word-tree min-w-0" :aria-label="t('word.tree')">
    <p v-if="!items.length" role="status" class="text-muted">
      {{ t('word.emptyTree') }}
    </p>
    <NTree
      v-else block-line :data="data" :render-label="renderLabel"
      :expanded-keys="expandedKeys" :selected-keys="selectedKeys"
      @update:expanded-keys="emit('update:expandedKeys', $event.map(String))"
      @update:selected-keys="emit('update:selectedKeys', $event.map(String))"
    />
  </div>
</template>

<style scoped>
.word-tree :deep(.n-tree-node) {
  min-height: var(--pw-control-height-large);
}
.word-tree :deep(.n-tree-node-content) {
  min-width: 0;
  white-space: normal;
}
.word-tree :deep(.n-tree-node-content__text) {
  min-width: 0;
  flex: 1;
}
.word-tree :deep(.n-tree-node-switcher) {
  min-width: var(--pw-control-height-large);
  min-height: var(--pw-control-height-large);
}
</style>
