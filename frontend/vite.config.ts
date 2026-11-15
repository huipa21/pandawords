import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import UnoCSS from 'unocss/vite'
import IconsResolver from 'unplugin-icons/resolver'
import Icons from 'unplugin-icons/vite'
import { NaiveUiResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vitest/config'
import { designCssPlugin } from './design-css-plugin.ts'
import { pwaPlugin } from './pwa-plugin.ts'

export default defineConfig({
  plugins: [
    designCssPlugin(),
    pwaPlugin(),
    UnoCSS(),
    vue(),
    Icons({ compiler: 'vue3' }),
    Components({
      dts: false,
      resolvers: [
        NaiveUiResolver(),
        IconsResolver({
          prefix: 'i',
          enabledCollections: ['lucide'],
        }),
      ],
    }),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'happy-dom',
    include: ['src/**/*.test.ts'],
  },
})
