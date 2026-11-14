import { createPinia } from 'pinia'
import { createApp } from 'vue'
import { configureApiAuth } from '@/api/client'
import { createAppI18n } from '@/i18n'
import { useAuthStore } from '@/stores/auth'
import App from './App.vue'
import { createAppRouter } from './router'
import 'virtual:pw-design.css'
import 'virtual:uno.css'

const pinia = createPinia()
const auth = useAuthStore(pinia)
configureApiAuth({
  getAccessToken: () => auth.accessToken,
  getSessionVersion: auth.getSessionVersion,
  refresh: auth.refresh,
  logout: auth.reset,
})

createApp(App)
  .use(pinia)
  .use(createAppI18n())
  .use(createAppRouter())
  .mount('#app')
