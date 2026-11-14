<script setup lang="ts">
import type { ThemeMode } from '@/design/tokens'
import { darkTheme, useMessage } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AppHeader from '@/components/app/AppHeader.vue'
import AppNavigation from '@/components/app/AppNavigation.vue'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import { darkThemeOverrides, themeOverrides } from '@/design/naive-theme'
import { radius, spacing, themes, typography } from '@/design/tokens'
import en from '@/i18n/dev-design/en.json'
import zhCN from '@/i18n/dev-design/zh-CN.json'
import WordComponentsPreview from './WordComponentsPreview.vue'

const { t } = useI18n({
  useScope: 'local',
  messages: { en, 'zh-CN': zhCN },
})
const { t: globalT } = useI18n({ useScope: 'global' })
const confirming = ref(false)
const message = useMessage()
const sample = ref('')
const selection = ref<ThemeMode>('light')
const modes = ['light', 'dark'] as const
const groups = ['colors', 'nodes', 'edges', 'ratings'] as const
const options = computed(() => modes.map(value => ({
  value,
  label: t(value),
})))

function themeStyle(mode: ThemeMode) {
  const theme = themes[mode]
  return Object.fromEntries(
    ([
      ['color', theme.colors],
      ['node', theme.nodes],
      ['edge', theme.edges],
      ['rating', theme.ratings],
      ['shadow', theme.shadows],
    ] as const).flatMap(([prefix, values]) =>
      Object.entries(values).map(([name, value]) => [`--pw-${prefix}-${name}`, value]),
    ),
  )
}

function colorVariable(group: typeof groups[number], name: string) {
  const prefix = {
    colors: 'color',
    nodes: 'node',
    edges: 'edge',
    ratings: 'rating',
  }[group]
  return `var(--pw-${prefix}-${name})`
}
</script>

<template>
  <div class="space-y-6">
    <header>
      <h1 class="m-0 text-2xl font-bold">
        {{ t('title') }}
      </h1>
      <p class="text-muted">
        {{ t('intro') }}
      </p>
    </header>
    <h2 class="text-xl font-semibold">
      {{ t('tokens') }}
    </h2>
    <div class="grid grid-cols-1 gap-6 xl:grid-cols-2">
      <NConfigProvider
        v-for="mode in modes" :key="mode"
        :theme="mode === 'dark' ? darkTheme : null"
        :theme-overrides="mode === 'dark' ? darkThemeOverrides : themeOverrides"
      >
        <section
          :data-preview-theme="mode" :data-theme="mode" :style="themeStyle(mode)"
          :aria-label="t(mode)" class="min-w-0 space-y-6 border border-base rounded-lg bg-page p-4 text-fg"
        >
          <h3 class="m-0 text-lg font-semibold">
            {{ t(mode) }}
          </h3>
          <section v-for="group in groups" :key="group">
            <h4 class="text-base font-semibold">
              {{ t(group) }}
            </h4>
            <div class="grid grid-cols-2 gap-3">
              <div v-for="(value, name) in themes[mode][group]" :key="name" class="min-w-0">
                <div
                  class="h-control-large rounded-sm border border-base"
                  :style="{ backgroundColor: colorVariable(group, name) }"
                />
                <code class="block break-words text-xs">{{ name }}</code>
                <code class="text-xs text-muted">{{ value }}</code>
              </div>
            </div>
          </section>
          <section>
            <h4 class="text-base font-semibold">
              {{ t('typography') }}
            </h4>
            <p
              v-for="(size, name) in typography.size" :key="name"
              class="break-words" :style="{ fontSize: `var(--pw-font-size-${name})` }"
            >
              <code class="text-xs">{{ name }} · {{ size }}</code>
              {{ t('sample') }}
            </p>
            <p
              v-for="(_, name) in typography.font" :key="name"
              :style="{ fontFamily: `var(--pw-font-${name})` }"
            >
              {{ name }} · {{ t(name === 'ipa' ? 'ipa' : 'sample') }}
            </p>
            <p
              v-for="(value, name) in typography.weight" :key="name"
              :style="{ fontWeight: `var(--pw-font-weight-${name})` }"
            >
              {{ name }} · {{ value }} · {{ t('sample') }}
            </p>
            <p
              v-for="(value, name) in typography.lineHeight" :key="name"
              :style="{ lineHeight: `var(--pw-line-height-${name})` }"
            >
              {{ name }} · {{ value }} · {{ t('sample') }}<br>{{ t('sample') }}
            </p>
          </section>
          <section>
            <h4 class="text-base font-semibold">
              {{ t('spacing') }}
            </h4>
            <div v-for="(value, name) in spacing" :key="name" class="my-2 flex items-center gap-3">
              <span class="bg-primary" :style="{ width: `var(--pw-space-${String(name).replace('.', '-')})`, height: 'var(--pw-space-4)' }" />
              <code class="text-sm">{{ name }} · {{ value }}</code>
            </div>
          </section>
          <section>
            <h4 class="text-base font-semibold">
              {{ t('radius') }}
            </h4>
            <div class="flex flex-wrap gap-3">
              <div
                v-for="(value, name) in radius" :key="name"
                class="bg-primary-soft p-4 text-primary"
                :style="{ borderRadius: `var(--pw-radius-${name})` }"
              >
                {{ name }} · {{ value }}
              </div>
            </div>
          </section>
          <section>
            <h4 class="text-base font-semibold">
              {{ t('shadows') }}
            </h4>
            <div class="flex flex-wrap gap-4">
              <div
                v-for="(_, name) in themes[mode].shadows" :key="name"
                class="rounded-md bg-raised p-6"
                :style="{ boxShadow: `var(--pw-shadow-${name})` }"
              >
                {{ t('shadows') }} · {{ name }}
              </div>
            </div>
          </section>
          <WordComponentsPreview />
          <section>
            <h4 class="text-base font-semibold">
              {{ t('naive') }}
            </h4>
            <NCard :title="t('naive')">
              <NForm label-placement="top">
                <NFormItem :label="t('name')" :label-props="{ for: `sample-${mode}` }">
                  <NInput v-model:value="sample" :input-props="{ id: `sample-${mode}` }" :placeholder="t('placeholder')" size="large" />
                </NFormItem>
                <NFormItem :label="t('theme')" :label-props="{ for: `selection-${mode}` }">
                  <NSelect v-model:value="selection" filterable :options="options" :input-props="{ 'id': `selection-${mode}`, 'aria-label': t('theme') }" size="large" />
                </NFormItem>
              </NForm>
              <div class="flex flex-wrap items-center gap-3">
                <NTooltip>
                  <template #trigger>
                    <NButton size="large" @click="message.success(t('message'))">
                      {{ t('action') }}
                    </NButton>
                  </template>
                  {{ t('tooltip') }}
                </NTooltip>
                <NTag type="success">
                  {{ t('tag') }}
                </NTag>
              </div>
              <div class="my-4" :aria-label="t('progress')">
                <NProgress type="line" :percentage="60" />
              </div>
              <NEmpty :description="t('empty')" />
            </NCard>
          </section>
        </section>
      </NConfigProvider>
    </div>
    <section class="space-y-4">
      <h2 class="text-xl font-semibold">
        {{ t('components') }}
      </h2>
      <p class="text-muted">
        {{ t('shell') }}
      </p>
      <h3 class="text-lg font-semibold">
        {{ t('header') }}
      </h3>
      <AppHeader />
      <h3 class="text-lg font-semibold">
        {{ t('navigation') }}
      </h3>
      <AppNavigation />
      <h3 class="text-lg font-semibold">
        {{ t('mobile') }}
      </h3>
      <AppNavigation mobile />
      <PageHeader :title="globalT('pages.users')" :subtitle="globalT('admin.protectionNotice')">
        <template #actions>
          <NButton size="large" @click="confirming = true">
            {{ globalT('admin.disable') }}
          </NButton>
        </template>
      </PageHeader>
      <EmptyState title-key="admin.empty">
        <template #action>
          <NButton size="large" @click="message.success(globalT('admin.saved'))">
            {{ globalT('admin.create') }}
          </NButton>
        </template>
      </EmptyState>
      <ErrorState :error="globalT('errors.transport')" @retry="message.success(globalT('admin.saved'))" />
      <ConfirmAction
        :show="confirming" title-key="admin.disable" content-key="admin.confirmNotice"
        :params="{ username: globalT('auth.username') }"
        @confirm="confirming = false" @cancel="confirming = false"
      />
    </section>
  </div>
</template>
