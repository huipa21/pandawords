import { createI18n } from 'vue-i18n'
import en from './en.json'
import zhCN from './zh-CN.json'

export function createAppI18n() {
  return createI18n({
    legacy: false,
    locale: 'zh-CN',
    fallbackLocale: 'en',
    messages: { en, 'zh-CN': zhCN },
  })
}
