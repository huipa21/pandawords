import antfu from '@antfu/eslint-config'
import unocss from '@unocss/eslint-plugin'
import noBlockedDynamicClasses from './eslint-rules/no-blocked-dynamic-classes.mjs'
import noRawStyleValues from './eslint-rules/no-raw-style-values.mjs'

export default antfu(
  {},
  {
    files: ['**/*.vue'],
    plugins: {
      pandawords: {
        rules: {
          'no-raw-style-values': noRawStyleValues,
          'no-blocked-dynamic-classes': noBlockedDynamicClasses,
        },
      },
      unocss,
    },
    rules: {
      'pandawords/no-raw-style-values': 'error',
      'pandawords/no-blocked-dynamic-classes': 'error',
      'unocss/blocklist': 'error',
    },
  },
)
