<script setup lang="ts">
import type { TreeLemma, TreeTable } from './treeAdapter'
import { computed, onMounted, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import LemmaTree from '@/components/word/LemmaTree.vue'
import { findTreeNode, treeView, updateTreeVisibility } from './treeAdapter'
import { useProjectErrors } from './useProject'

const props = defineProps<{ projectId: string, sourceLang: string }>()
const emit = defineEmits<{ add: [] }>()
const { t } = useI18n()
const errorText = useProjectErrors()
const items = ref<TreeLemma[]>([])
const page = ref(1)
const total = ref(0)
const pageSize = ref(20)
const loaded = ref(false)
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const busy = ref(false)
const showHidden = ref(false)
const undo = ref<{ table: TreeTable, id: string, hidden: boolean }>()
const pages = computed(() => Math.max(1, Math.ceil(total.value / pageSize.value)))
const view = computed(() => treeView(items.value, showHidden.value, props.sourceLang))
let requested = 1
let request = 0
let disposed = false

async function load(target = page.value) {
  const current = ++request
  requested = target
  loading.value = true
  error.value = ''
  try {
    const result = await api.GET('/api/projects/{project_id}/tree', {
      params: {
        path: { project_id: props.projectId },
        query: { page: target, page_size: 20, include_hidden: true },
      },
    })
    if (disposed || current !== request)
      return
    if (result.data) {
      items.value = result.data.items
      page.value = result.data.page
      total.value = result.data.total
      pageSize.value = result.data.page_size
      loaded.value = true
    }
    else {
      error.value = errorText(result.error, result.response.status)
    }
  }
  catch {
    if (!disposed && current === request)
      error.value = t('errors.transport')
  }
  finally {
    if (!disposed && current === request)
      loading.value = false
  }
}

async function setVisibility(table: TreeTable, id: string, hidden: boolean, isUndo = false) {
  if (busy.value)
    return
  const previous = findTreeNode(items.value, table, id)?.hidden ?? (isUndo
    ? !hidden
    : undefined)
  if (previous === undefined)
    return
  busy.value = true
  actionError.value = ''
  ++request
  loading.value = false
  try {
    const result = await api.PATCH('/api/projects/{project_id}/tree/{table}/{target_id}/visibility', {
      params: {
        path: { project_id: props.projectId, table, target_id: id },
      },
      body: { hidden },
    })
    if (disposed)
      return
    if (!result.data) {
      actionError.value = errorText(result.error, result.response.status)
      return
    }
    updateTreeVisibility(items.value, table, id, result.data.hidden)
    undo.value = isUndo
      ? undefined
      : { table, id, hidden: previous }
    await load()
  }
  catch {
    if (!disposed)
      actionError.value = t('errors.transport')
  }
  finally {
    busy.value = false
  }
}

function node(table: TreeTable, id: string) {
  return findTreeNode(items.value, table, id)
}

function nodeName(table: TreeTable, id: string) {
  const item = node(table, id)
  if (!item)
    return id
  const record = 'lemma' in item
    ? item.lemma
    : 'lexeme' in item
      ? item.lexeme
      : item.sense
  const name = record.fields.text ?? record.fields.pos ?? record.fields.definition
  return typeof name === 'string'
    ? name
    : id
}

onMounted(() => load())
onScopeDispose(() => {
  disposed = true
  request++
})
defineExpose({
  refresh: () => load(),
})
</script>

<template>
  <section class="grid min-w-0 gap-4" data-testid="project-tree">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h2 class="m-0 text-xl">
        {{ t('projects.treeTitle') }}
      </h2>
      <div class="flex flex-wrap items-center gap-3">
        <NSpin v-if="loaded && loading" size="small" :aria-label="t('common.loading')" />
        <NButton size="large" data-testid="project-tree-show-hidden" :aria-pressed="showHidden" @click="showHidden = !showHidden">
          {{ t(showHidden ? 'projects.treeVisibleOnly' : 'projects.treeShowHidden') }}
        </NButton>
      </div>
    </div>
    <p v-if="showHidden" class="m-0 text-muted">
      {{ t('projects.treeHiddenHint') }}
    </p>
    <div v-if="undo" role="status" class="flex flex-wrap items-center gap-3" data-testid="project-tree-undo">
      <span>{{ t('projects.treeChanged') }}</span>
      <NButton size="large" :disabled="busy" @click="setVisibility(undo.table, undo.id, undo.hidden, true)">
        {{ t('projects.treeUndo') }}
      </NButton>
    </div>
    <p v-if="actionError" role="alert" class="text-error" data-testid="project-tree-action-error">
      {{ actionError }}
    </p>
    <div v-if="loading && !loaded" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="4" />
    </div>
    <ErrorState v-if="error" :error="error" :loading="loading" @retry="load(requested)" />
    <EmptyState v-if="loaded && !view.length && !error" :title-key="total ? 'projects.treeNoVisible' : 'projects.treeEmpty'" :desc-key="total ? 'projects.treeHiddenHint' : 'projects.treeEmptyHint'">
      <template v-if="!total" #action>
        <NButton size="large" @click="emit('add')">
          {{ t('addWord.title') }}
        </NButton>
      </template>
    </EmptyState>
    <LemmaTree v-if="view.length" :key="page" :items="view" default-expand-all>
      <template #actions="{ table, id }">
        <div v-if="node(table, id)" class="flex flex-wrap items-center gap-2" :data-tree-table="table" :data-tree-id="id">
          <RouterLink v-if="table === 'lemma'" :to="`/words/${encodeURIComponent(id)}`" class="tree-link inline-flex items-center text-primary focus-visible:pw-focus-ring" data-testid="project-tree-word-link">
            {{ t('projects.treeWordDetail') }}
          </RouterLink>
          <NTag v-if="node(table, id)?.hidden">
            {{ t('projects.treeHiddenDirect') }}
          </NTag>
          <NTag v-else-if="node(table, id)?.effective_hidden">
            {{ t('projects.treeHiddenAncestor') }}
          </NTag>
          <NButton
            size="large" :disabled="busy" data-testid="project-tree-visibility"
            :aria-label="t(node(table, id)?.hidden ? 'projects.treeRestoreNamed' : 'projects.treeHideNamed', { name: nodeName(table, id) })"
            @click="setVisibility(table, id, !node(table, id)?.hidden)"
          >
            {{ t(node(table, id)?.hidden ? 'word.unhide' : 'word.hide') }}
          </NButton>
        </div>
      </template>
    </LemmaTree>
    <nav v-if="loaded && total" class="flex flex-wrap items-center justify-between gap-3" :aria-label="t('projects.treePagination')">
      <NButton size="large" :disabled="page <= 1 || loading || busy" data-testid="project-tree-previous" @click="load(page - 1)">
        {{ t('common.previous') }}
      </NButton>
      <span>{{ t('projects.treePage', { page, pages, total }) }}</span>
      <NButton size="large" :disabled="page >= pages || loading || busy" data-testid="project-tree-next" @click="load(page + 1)">
        {{ t('common.next') }}
      </NButton>
    </nav>
  </section>
</template>

<style scoped>
.tree-link {
  min-height: var(--pw-layout-touch-target);
}
</style>
