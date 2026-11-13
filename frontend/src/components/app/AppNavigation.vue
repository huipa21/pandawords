<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ mobile?: boolean }>()
const { t } = useI18n()
const links = computed(() => props.mobile
  ? [
      { to: '/projects', key: 'projects' },
      { to: '/review', key: 'review' },
      { to: '/words', key: 'words' },
      { to: '/settings', key: 'me' },
    ]
  : [
      { to: '/projects', key: 'projects' },
      { to: '/words', key: 'words' },
      { to: '/review', key: 'review' },
      { to: '/settings', key: 'settings' },
    ])
</script>

<template>
  <nav :aria-label="t(mobile ? 'navigation.mobile' : 'navigation.sidebar')" class="flex gap-2" :class="mobile ? 'mobile-navigation justify-around' : 'flex-col'">
    <RouterLink
      v-for="link in links" :key="link.key" v-slot="{ href, navigate, isActive }" :to="link.to" custom
    >
      <a
        :href="href" :aria-current="isActive ? 'page' : undefined"
        class="navigation-link flex items-center justify-center rounded-md no-underline focus-visible:pw-focus-ring"
        :class="[mobile ? 'flex-1 flex-col gap-0 px-2 py-1 text-xs' : 'justify-start gap-2 p-2 text-sm', isActive ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-raised']"
        @click="navigate"
      >
        <i-lucide-folder v-if="link.key === 'projects'" class="navigation-icon" aria-hidden="true" />
        <i-lucide-book-open v-else-if="link.key === 'words'" class="navigation-icon" aria-hidden="true" />
        <i-lucide-graduation-cap v-else-if="link.key === 'review'" class="navigation-icon" aria-hidden="true" />
        <i-lucide-user v-else-if="link.key === 'me'" class="navigation-icon" aria-hidden="true" />
        <i-lucide-settings v-else class="navigation-icon" aria-hidden="true" />
        {{ t(`navigation.${link.key}`) }}
      </a>
    </RouterLink>
  </nav>
</template>

<style scoped>
.navigation-link {
  min-height: var(--pw-layout-touch-target);
}
.mobile-navigation {
  height: var(--pw-layout-bottom-nav-height);
}
.navigation-icon {
  width: var(--pw-icon-size-nav);
  height: var(--pw-icon-size-nav);
}
</style>
