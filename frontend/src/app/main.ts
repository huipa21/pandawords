import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { createAppI18n } from '@/i18n'
import App from './App.vue'
import { createAppRouter } from './router'
import 'virtual:pw-design.css'
import 'virtual:uno.css'

createApp(App)
  .use(createPinia())
  .use(createAppI18n())
  .use(createAppRouter())
  .mount('#app')
