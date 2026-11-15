<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import ProtectedImage from './ProtectedImage.vue'
import { useSenseImages } from './useSenseImages'

const props = defineProps<{ senseId: string }>()
const { t } = useI18n()
const { items, results, busy, error, upload, search, select, remove, retry } = useSenseImages(() => props.senseId)
const query = ref('')
const removing = ref<string>()
function choose(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file)
    void upload(file)
  input.value = ''
}
async function confirmRemove() {
  if (removing.value)
    await remove(removing.value)
  removing.value = undefined
}
</script>

<template>
  <section class="grid gap-4" :aria-label="t('images.title')" data-testid="sense-images">
    <h3 class="font-semibold">
      {{ t('images.title') }}
    </h3>
    <p class="text-sm text-muted">
      {{ t('images.limits') }}
    </p>
    <label class="grid gap-2">
      <span>{{ t('images.upload') }}</span>
      <input type="file" accept="image/jpeg,image/png,image/webp,image/gif" class="min-h-12 max-w-full" :disabled="busy" @change="choose">
    </label>
    <NSpin v-if="busy" :aria-label="t('common.loading')" />
    <ErrorState v-if="error" :error="error" :loading="busy" @retry="retry" />
    <p v-if="!busy && !items.length">
      {{ t('images.empty') }}
    </p>
    <div v-for="image in items" :key="image.id" class="grid gap-3 rounded-lg border border-border p-3">
      <ProtectedImage :media-id="image.id" />
      <p v-if="image.attribution" class="break-words text-sm text-muted">
        {{ image.attribution }}
      </p>
      <NButton size="large" :disabled="busy" @click="removing = image.id">
        {{ t('images.remove') }}
      </NButton>
    </div>
    <form class="grid gap-3" @submit.prevent="search(query)">
      <label class="grid gap-2">
        <span>{{ t('images.query') }}</span>
        <NInput v-model:value="query" :maxlength="100" :disabled="busy" :placeholder="t('images.query')" />
      </label>
      <NButton attr-type="submit" size="large" :disabled="busy || !query.trim()">
        {{ t('images.search') }}
      </NButton>
    </form>
    <p v-if="results && !results.results.length">
      {{ t('images.noResults') }}
    </p>
    <div v-for="result in results?.results" :key="result.id" class="grid gap-3 rounded-lg border border-border p-3">
      <a :href="result.source_page" target="_blank" rel="noopener noreferrer" class="min-h-12 text-primary underline">
        {{ t('images.source', { creator: result.creator, id: result.id }) }}
      </a>
      <p class="break-words text-sm text-muted">
        {{ result.attribution }}
      </p>
      <NButton size="large" :disabled="busy" @click="select(result.id)">
        {{ t('images.select') }}
      </NButton>
    </div>
    <ConfirmAction
      :show="!!removing" title-key="images.remove" content-key="images.removeConfirm"
      :loading="busy" @confirm="confirmRemove" @cancel="removing = undefined"
    />
  </section>
</template>
