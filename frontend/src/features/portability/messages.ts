import { useI18n } from 'vue-i18n'
import en from '@/i18n/portability/en.json'
import zhCN from '@/i18n/portability/zh-CN.json'

/**
 * Portability and site-backup strings ship with the lazy feature chunks instead of the initial
 * bundle; they are merged into the global messages on first use.
 */
export function usePortabilityI18n() {
  const i18n = useI18n({ useScope: 'global' })
  if (!i18n.te('portability.chooseFile', 'en')) {
    i18n.mergeLocaleMessage('en', en)
    i18n.mergeLocaleMessage('zh-CN', zhCN)
  }
  return i18n
}
