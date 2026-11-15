<script setup lang="ts">
import type { ImportSummary, RestoreSummary } from './requests'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ kind: 'project' | 'user', summary: ImportSummary | RestoreSummary }>()
const { t } = useI18n()
const sum = (counts: Record<string, number>) => Object.values(counts).reduce((total, value) => total + value, 0)
const restore = computed(() => 'already_restored' in props.summary
  ? props.summary
  : undefined)
const totals = computed(() => (['created', 'merged', 'skipped'] as const).map(key => ({
  key,
  total: sum(props.summary[key]),
  kinds: Object.entries(props.summary[key]).filter(([, count]) => count > 0),
})))
const notices = computed(() => [
  ...props.summary.conflicts,
  ...props.summary.warnings,
])
</script>

<template>
  <NAlert type="success" :title="t(restore?.already_restored ? 'portability.alreadyRestored' : `portability.${kind}.success`)" data-testid="archive-summary">
    <div class="grid gap-3">
      <p class="m-0">
        {{ t(summary.progress_imported ? 'portability.summary.progressOn' : 'portability.summary.progressOff') }}
        {{ t(summary.same_source ? 'portability.summary.sameSource' : 'portability.summary.otherSource') }}
      </p>
      <p class="m-0">
        {{ t('portability.summary.projects', { count: summary.project_ids.length }) }}
      </p>
      <dl class="m-0 flex flex-wrap gap-4">
        <div v-for="row in totals" :key="row.key">
          <dt class="text-sm text-muted">
            {{ t(`portability.summary.${row.key}`) }}
          </dt>
          <dd class="m-0 font-semibold" :title="row.kinds.map(([name, count]) => `${name}: ${count}`).join(', ')">
            {{ row.total }}
          </dd>
        </div>
      </dl>
      <template v-if="restore">
        <p v-if="restore.preferences_restored.length" class="m-0 text-sm">
          {{ t('portability.summary.preferencesRestored', { fields: restore.preferences_restored.join(', ') }) }}
        </p>
        <p v-if="restore.preferences_kept.length" class="m-0 text-sm">
          {{ t('portability.summary.preferencesKept', { fields: restore.preferences_kept.join(', ') }) }}
        </p>
      </template>
      <details v-if="notices.length">
        <summary class="cursor-pointer">
          {{ t('portability.summary.notices', { count: notices.length }) }}
        </summary>
        <ul class="m-0 break-words pl-4 text-sm">
          <li v-for="(notice, index) in notices" :key="index">
            {{ notice }}
          </li>
        </ul>
      </details>
      <RouterLink
        v-if="kind === 'project' && summary.project_ids[0]"
        :to="{ name: 'project', params: { id: summary.project_ids[0] } }"
        class="text-primary focus-visible:pw-focus-ring" data-testid="archive-open-project"
      >
        {{ t('portability.project.open') }}
      </RouterLink>
    </div>
  </NAlert>
</template>
