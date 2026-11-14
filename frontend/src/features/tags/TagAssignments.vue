<script setup lang="ts">
import type { components } from '@/api/schema'
import { computed, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { api } from '@/api/client'
import ErrorState from '@/components/app/ErrorState.vue'

type Tag = components['schemas']['TagRead']
type Assignment = components['schemas']['TagAssignmentRead']
const props = defineProps<{ target: components['schemas']['TagAssignment'] }>()
const { t } = useI18n()
const tags = ref<Tag[]>([])
const assigned = ref<Assignment[]>([])
const selected = ref<string>()
const name = ref('')
const error = ref('')
const loading = ref(true)
const busy = ref(false)
const removed = ref<Tag>()
const options = computed(() => tags.value.filter(tag =>
  !assigned.value.some(item => item.tag.id === tag.id)
  && !(props.target.target_table === 'tag' && props.target.target_id === tag.id))
  .map(tag => ({ label: tag.name, value: tag.id })))
let disposed = false
onScopeDispose(() => disposed = true)

async function load() {
  if (busy.value)
    return
  loading.value = true
  error.value = ''
  try {
    const [all, memberships] = await Promise.all([
      api.GET('/api/tags'),
      api.GET('/api/tags/assignments', {
        params: { query: props.target },
      }),
    ])
    if (disposed)
      return
    if (!all.data || !memberships.data)
      throw new Error('load')
    tags.value = all.data
    assigned.value = memberships.data
  }
  catch {
    if (!disposed)
      error.value = t('tags.failed')
  }
  finally {
    if (!disposed)
      loading.value = false
  }
}
async function mutate(action: 'create' | 'assign' | 'remove', tag?: Tag) {
  if (busy.value || loading.value)
    return
  const id = tag?.id ?? selected.value
  if (action !== 'create' && !id)
    return
  busy.value = true
  error.value = ''
  try {
    if (action === 'create') {
      const result = await api.POST('/api/tags', {
        body: { name: name.value, kind: 'custom' },
      })
      if (disposed)
        return
      if (!result.data)
        throw new Error('create')
      tags.value.push(result.data)
      selected.value = result.data.id
      name.value = ''
    }
    else {
      const params = {
        path: { id: id! },
      }
      const result = action === 'remove'
        ? await api.DELETE('/api/tags/{id}/members', {
            params: { ...params, query: props.target },
          })
        : await api.PUT('/api/tags/{id}/members', { params, body: props.target })
      if (disposed)
        return
      if (!result.response.ok) {
        const code = (result.error as { code?: string } | undefined)?.code
        error.value = t(code === 'tag.cycle'
          ? 'tags.cycle'
          : 'tags.failed')
        return
      }
      if (action === 'remove') {
        assigned.value = assigned.value.filter(item => item.tag.id !== id || item.readonly)
        removed.value = tag
      }
      else {
        const saved = tag ?? tags.value.find(item => item.id === id)
        if (saved && !assigned.value.some(item => item.tag.id === id && !item.readonly))
          assigned.value.push({ tag: saved, readonly: false })
        selected.value = undefined
        if (removed.value?.id === id)
          removed.value = undefined
      }
    }
  }
  catch {
    if (!disposed)
      error.value = t('tags.failed')
  }
  finally {
    if (!disposed)
      busy.value = false
  }
}
void load()
</script>

<template>
  <section class="grid gap-3" data-testid="tag-assignments" :aria-label="t('tags.title')">
    <h3 class="font-semibold">
      {{ t('tags.title') }}
    </h3>
    <RouterLink to="/tags" class="text-primary underline">
      {{ t('tags.manage') }}
    </RouterLink>
    <NSkeleton v-if="loading" text :repeat="2" />
    <ErrorState v-if="error" :error="error" :loading="loading || busy" @retry="load" />
    <p v-if="!loading && !assigned.length" class="text-muted">
      {{ t('tags.empty') }}
    </p>
    <div v-for="(item, index) in assigned" :key="`${item.tag.id}:${index}`" class="flex flex-wrap items-center gap-3">
      <NTag>{{ item.tag.name }}</NTag>
      <span v-if="item.readonly" class="text-muted">{{ t('tags.source') }}</span>
      <NButton v-else size="large" :disabled="busy || loading" data-testid="tag-remove" @click="mutate('remove', item.tag)">
        {{ t('tags.remove') }}
      </NButton>
    </div>
    <NButton v-if="removed" size="large" :disabled="busy || loading" data-testid="tag-undo" @click="mutate('assign', removed)">
      {{ t('tags.undo', { name: removed.name }) }}
    </NButton>
    <NFormItem :label="t('tags.choose')" :label-props="{ for: `tag-choice-${target.target_id}` }">
      <NSelect v-model:value="selected" :options="options" :disabled="loading || busy" :input-props="{ id: `tag-choice-${target.target_id}` }" />
    </NFormItem>
    <NButton size="large" :disabled="!selected || busy || loading" :loading="busy" data-testid="tag-assign" @click="mutate('assign')">
      {{ t('tags.assign') }}
    </NButton>
    <NFormItem :label="t('tags.name')" :label-props="{ for: `tag-name-${target.target_id}` }">
      <NInput v-model:value="name" :input-props="{ id: `tag-name-${target.target_id}` }" :maxlength="200" :disabled="loading || busy" data-testid="tag-name" />
    </NFormItem>
    <NButton size="large" :disabled="!name.trim() || busy || loading" :loading="busy" data-testid="tag-create" @click="mutate('create')">
      {{ t('tags.create') }}
    </NButton>
  </section>
</template>
