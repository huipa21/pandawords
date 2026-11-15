<script setup lang="ts">
import type { LexemeView, Pronunciation } from './types'
import PosBadge from './PosBadge.vue'
import PronunciationChip from './PronunciationChip.vue'
import SenseItem from './SenseItem.vue'

defineProps<{ lexeme: LexemeView, editable?: boolean }>()
const emit = defineEmits<{
  edit: [id: string]
  hide: [id: string, hidden: boolean]
  note: [id: string]
  play: [pronunciation: Pronunciation]
}>()
</script>

<template>
  <section class="min-w-0 space-y-3">
    <div class="flex flex-wrap items-center gap-3">
      <PosBadge :pos="lexeme.pos" />
      <PronunciationChip
        v-for="pronunciation in lexeme.pronunciations" :key="pronunciation.id"
        v-bind="pronunciation" @play="emit('play', pronunciation)"
      />
    </div>
    <SenseItem
      v-for="sense in lexeme.senses" :key="sense.id" :sense="sense" :editable="editable"
      @edit="emit('edit', $event)" @hide="(id, hidden) => emit('hide', id, hidden)" @note="emit('note', $event)"
    />
  </section>
</template>
