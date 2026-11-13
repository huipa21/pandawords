import { defineConfig, presetWind3 } from 'unocss'
import { unoTheme } from './src/design/uno-theme.ts'
import { blockedUtilityReason } from './src/design/utility-blocklist.ts'

export default defineConfig({
  presets: [
    presetWind3(),
  ],
  extendTheme: theme => ({
    ...theme,
    ...unoTheme,
  }),
  blocklist: [
    [
      candidate => Boolean(blockedUtilityReason(candidate)),
      {
        message: candidate => blockedUtilityReason(candidate) ?? '',
      },
    ],
  ],
  rules: [
    [
      'pw-focus-ring',
      {
        'outline': 'var(--pw-focus-ring)',
        'outline-offset': 'var(--pw-focus-ring-offset)',
      },
    ],
  ],
})
