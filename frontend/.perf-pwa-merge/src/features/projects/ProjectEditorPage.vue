<script setup lang="ts">
import type { ProjectCreate } from './useProject'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import ProjectForm from './ProjectForm.vue'
import { useProject } from './useProject'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const id = computed(() => typeof route.params.id === 'string'
  ? route.params.id
  : undefined)
const { project, loading, busy, loadError, fields, load, save } = useProject(() => id.value)

async function submit(body: ProjectCreate) {
  const saved = await save(body)
  if (saved) {
    await router.push({
      name: 'project',
      params: { id: saved.id },
    })
  }
}

function cancel() {
  return router.push(id.value
    ? {
        name: 'project',
        params: { id: id.value },
      }
    : { name: 'projects' })
}
</script>

<template>
  <section class="grid gap-6" data-testid="project-editor">
    <PageHeader :title="t(id ? 'projects.edit' : 'projects.create')" />
    <div v-if="loading" role="status" :aria-label="t('common.loading')">
      <NSkeleton text :repeat="6" />
    </div>
    <ErrorState v-else-if="loadError" :error="loadError" @retry="load" />
    <NCard v-else-if="!id || project" class="max-w-reading">
      <ProjectForm :key="id ?? 'create'" :initial="project" :busy="busy" :fields="fields" :save="submit" @cancel="cancel" />
    </NCard>
  </section>
</template>
