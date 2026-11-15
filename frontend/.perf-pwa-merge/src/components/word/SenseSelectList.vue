<script setup lang="ts">
import type { LexemeView } from './types'
import { computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import PosBadge from './PosBadge.vue'
import SenseItem from './SenseItem.vue'

const props = defineProps<{ candidates: LexemeView[], selected?: string[] }>()
const emit = defineEmits<{ 'update:selected': [ids: string[]] }>()
const { t } = useI18n()
const defaults = computed(() => props.candidates.flatMap(lexeme =>
  lexeme.senses.filter(sense => sense.common && !sense.hidden).map(sense => sense.id),
))
const effective = computed(() => props.selected ?? defaults.value)
watch(defaults, (ids) => {
  if (props.selected === undefined)
    emit('update:selected', ids)
}, { immediate: true })
function select(id: string, checked: boolean) {
  const ids = new Set(effective.value)
  if (checked)
    ids.add(id)
  else
    ids.delete(id)
  emit('update:selected', [...ids])
}
</script>

<template>
  <div class="space-y-4" role="group" :aria-label="t('word.selectSenses')">
    <p v-if="!candidates.some(lexeme => lexeme.senses.length)" role="status" class="text-muted">
      {{ t('word.emptySenses') }}
    </p>
    <section v-for="lexeme in candidates" :key="lexeme.id" class="space-y-3">
      <PosBadge :pos="lexeme.pos" />
      <SenseItem
        v-for="sense in lexeme.senses" :key="sense.id" :sense="sense" selectable
        :selected="effective.includes(sense.id)" @update:selected="select(sense.id, $event)"
      />
    </section>
  </div>
</template>
