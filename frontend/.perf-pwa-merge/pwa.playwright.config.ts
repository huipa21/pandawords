import { defineConfig, devices } from '@playwright/test'

const port = Number(process.env.PWA_TEST_PORT ?? 4179)
if (!Number.isInteger(port) || port < 1 || port > 65_535)
  throw new Error('PWA_TEST_PORT must be a valid TCP port')
const origin = `http://127.0.0.1:${port}`

export default defineConfig({
  testDir: './pwa',
  testMatch: '**/*.spec.ts',
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: 'list',
  use: {
    ...devices['Desktop Chrome'],
    baseURL: origin,
    trace: 'off',
    video: 'off',
    screenshot: 'off',
  },
  webServer: {
    command: `pnpm exec vite preview --host 127.0.0.1 --port ${port} --strictPort`,
    url: origin,
    reuseExistingServer: false,
  },
})
