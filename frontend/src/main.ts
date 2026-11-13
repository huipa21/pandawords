import { createApp } from 'vue'
import App from '@/App.vue'
import { createAppI18n } from '@/i18n'
import 'virtual:pw-design.css'
import 'virtual:uno.css'

createApp(App).use(createAppI18n()).mount('#app')
