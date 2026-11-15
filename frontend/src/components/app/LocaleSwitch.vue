<script setup lang="ts">
import { NButton, NDropdown } from 'naive-ui'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { layout } from '@/design/tokens'
import { usePreferencesStore } from '@/stores/preferences'

const preferences = usePreferencesStore()
const { t } = useI18n()
const show = ref(false)
const options = computed(() => [
  {
    key: 'en',
    label: t('preferences.english'),
  },
  {
    key: 'zh-CN',
    label: t('preferences.chinese'),
  },
])

function selectLocale(key: string) {
  if (key === 'en' || key === 'zh-CN')
    preferences.locale = key
}
</script>

<template>
  <NDropdown v-model:show="show" trigger="click" size="large" :menu-props="() => ({ role: 'menu' })" :node-props="() => ({ role: 'menuitem' })" :theme-overrides="{ optionHeightLarge: layout.touchTarget }" :options="options" :value="preferences.locale" @select="selectLocale">
    <NButton
      quaternary circle size="large" aria-haspopup="menu" :aria-expanded="show"
      :aria-label="t('preferences.localeAction')"
      :title="t('preferences.localeAction')"
    >
      <template #icon>
        <i-lucide-languages aria-hidden="true" />
      </template>
    </NButton>
  </NDropdown>
</template>
