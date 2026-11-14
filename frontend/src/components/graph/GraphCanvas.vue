<script setup lang="ts">
import type { Core } from 'cytoscape'
import type { GraphElements, GraphLayout } from './types'
import type { ThemeMode } from '@/design/tokens'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import fcose from 'cytoscape-fcose'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { graphMetrics } from '@/design/tokens'
import { usePreferencesStore } from '@/stores/preferences'
import { graphStyle } from './cytoscape-style'

const props = withDefaults(defineProps<{
  elements: GraphElements
  layout?: GraphLayout
  focusId?: string
  theme?: ThemeMode
}>(), { layout: 'fcose' })
const emit = defineEmits<{ select: [id: string], expand: [id: string] }>()
const { t } = useI18n()
const preferences = usePreferencesStore()
const mode = computed(() => props.theme ?? preferences.resolvedTheme)
const host = ref<HTMLElement>()
let cy: Core | undefined
let observer: ResizeObserver | undefined
cytoscape.use(fcose)
cytoscape.use(dagre)

function render() {
  if (!cy)
    return
  cy.elements().remove()
  cy.add([
    ...props.elements.nodes.map(node => ({
      data: node,
      classes: node.id === props.focusId
        ? 'focus'
        : '',
    })),
    ...props.elements.edges.map(edge => ({ data: edge })),
  ])
  const options = { name: props.layout, animate: false }
  cy.layout(options).run()
}
function fit() {
  cy?.resize()
  cy?.fit()
}
onMounted(() => {
  cy = cytoscape({
    container: host.value,
    elements: [],
    style: graphStyle(mode.value),
  })
  cy.on('tap', 'node', event => emit('select', event.target.id()))
  cy.on('dbltap', 'node', event => emit('expand', event.target.id()))
  render()
  observer = new ResizeObserver(fit)
  if (host.value)
    observer.observe(host.value)
})
watch(() => [props.elements, props.layout, props.focusId], render)
watch(mode, () => cy?.style(graphStyle(mode.value)))
onBeforeUnmount(() => {
  observer?.disconnect()
  cy?.destroy()
})
defineExpose({ fit })
</script>

<template>
  <section :aria-label="t('graph.canvas')" class="min-w-0 space-y-3" data-testid="graph-canvas">
    <div ref="host" class="graph-host border border-base rounded-lg bg-surface" :style="{ height: graphMetrics.canvasHeight }" aria-hidden="true" />
    <details>
      <summary class="min-h-12 cursor-pointer py-3 focus-visible:outline">
        {{ t('graph.accessibleNodes', { count: elements.nodes.length }) }}
      </summary>
      <ul class="m-0 list-none space-y-2 p-0">
        <li v-for="node in elements.nodes" :key="node.id" class="flex flex-wrap items-center gap-2">
          <NButton size="large" :aria-pressed="node.id === focusId" @click="emit('select', node.id)">
            {{ node.label }} · {{ t(`graph.nodes.${node.type}`) }}
          </NButton>
          <NButton size="large" :aria-label="t('graph.expandNode', { label: node.label })" @click="emit('expand', node.id)">
            {{ t('graph.expand') }}
          </NButton>
        </li>
      </ul>
    </details>
  </section>
</template>
