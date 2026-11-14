<script setup lang="ts">
import type { components } from '@/api/schema'
import { onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import TagAssignments from './TagAssignments.vue'

type Tag = components['schemas']['TagRead']
const { t } = useI18n()
const tags = ref<Tag[]>([])
const name = ref('')
const editing = ref<Tag>()
const removing = ref<Tag>()
const hierarchy = ref<Tag>()
const loading = ref(false)
const busy = ref(false)
const error = ref('')
let disposed = false
onScopeDispose(() => disposed = true)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const result = await api.GET('/api/tags')
    if (!disposed) {
      if (result.data)
        tags.value = result.data
      else
        error.value = t('tags.failed')
    }
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
function edit(tag: Tag) {
  editing.value = tag
  name.value = tag.name
}
async function save() {
  if (busy.value || !name.value.trim())
    return
  busy.value = true
  error.value = ''
  try {
    const result = editing.value
      ? await api.PATCH('/api/tags/{id}', {
          params: {
            path: { id: editing.value.id },
          },
          body: { name: name.value },
        })
      : await api.POST('/api/tags', {
          body: { name: name.value, kind: 'custom' },
        })
    if (disposed)
      return
    if (result.data) {
      tags.value = [
        ...tags.value.filter(tag => tag.id !== result.data.id),
        result.data,
      ]
      editing.value = undefined
      name.value = ''
    }
    else {
      error.value = t('tags.failed')
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
async function remove() {
  if (busy.value || !removing.value)
    return
  busy.value = true
  error.value = ''
  try {
    const result = await api.DELETE('/api/tags/{id}', {
      params: {
        path: { id: removing.value.id },
      },
    })
    if (disposed)
      return
    if (result.response.ok) {
      tags.value = tags.value.filter(tag => tag.id !== removing.value?.id)
      if (hierarchy.value?.id === removing.value.id)
        hierarchy.value = undefined
      if (editing.value?.id === removing.value.id) {
        editing.value = undefined
        name.value = ''
      }
      removing.value = undefined
    }
    else {
      error.value = t(result.response.status === 409
        ? 'tags.protected'
        : 'tags.failed')
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
  <section class="grid gap-4">
    <PageHeader :title="t('tags.title')">
      <template #actions>
        <NButton size="large" :disabled="loading || busy" @click="load">
          {{ t('tags.refresh') }}
        </NButton>
      </template>
    </PageHeader>
    <NSkeleton v-if="loading" text :repeat="3" />
    <ErrorState v-if="error" :error="error" :loading="busy || loading" @retry="load" />
    <p v-if="!loading && !tags.length" class="text-muted">
      {{ t('tags.empty') }}
    </p>
    <NCard v-for="tag in tags" :key="tag.id">
      <div class="flex flex-wrap items-center gap-3">
        <NTag>{{ tag.name }}</NTag>
        <span>{{ t(`tags.kinds.${tag.kind}`) }}</span>
        <span v-if="tag.readonly" class="text-muted">{{ t('tags.source') }}</span>
        <NButton v-if="!tag.readonly" size="large" :disabled="busy || loading" @click="edit(tag)">
          {{ t('tags.edit') }}
        </NButton>
        <NButton v-if="!tag.readonly" size="large" :disabled="busy || loading" @click="removing = tag">
          {{ t('tags.delete') }}
        </NButton>
        <NButton size="large" :disabled="busy || loading" @click="hierarchy = hierarchy?.id === tag.id ? undefined : tag">
          {{ t('tags.parents') }}
        </NButton>
      </div>
    </NCard>
    <TagAssignments v-if="hierarchy" :key="hierarchy.id" :target="{ target_table: 'tag', target_id: hierarchy.id }" />
    <NForm @submit.prevent="save">
      <NFormItem :label="t('tags.name')" :label-props="{ for: 'tag-editor-name' }">
        <NInput v-model:value="name" :input-props="{ id: 'tag-editor-name' }" :maxlength="200" :disabled="busy || loading" />
      </NFormItem>
      <div class="flex gap-3">
        <NButton size="large" attr-type="submit" :disabled="!name.trim() || busy || loading" :loading="busy">
          {{ t(editing ? 'tags.save' : 'tags.create') }}
        </NButton>
        <NButton v-if="editing" size="large" :disabled="busy" @click="editing = undefined; name = ''">
          {{ t('tags.cancel') }}
        </NButton>
      </div>
    </NForm>
    <ConfirmAction :show="!!removing" title-key="tags.delete" content-key="tags.deleteConfirm" :loading="busy" @confirm="remove" @cancel="removing = undefined" />
  </section>
</template>
