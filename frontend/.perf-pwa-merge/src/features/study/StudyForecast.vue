<script setup lang="ts">
import type { components } from '@/api/schema'
import { useI18n } from 'vue-i18n'

defineProps<{ days: components['schemas']['ForecastDay'][] }>()
const { t, locale, n } = useI18n()
function date(value: string) {
  return new Intl.DateTimeFormat(locale.value, { month: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`))
}
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full text-left">
      <caption class="mb-3 text-left font-semibold">
        {{ t('study.forecast') }}
      </caption>
      <thead>
        <tr>
          <th scope="col" class="p-2">
            {{ t('study.date') }}
          </th>
          <th scope="col" class="p-2">
            {{ t('study.scheduled') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="day in days" :key="day.date">
          <th scope="row" class="p-2 font-normal">
            <time :datetime="day.date">{{ date(day.date) }}</time>
          </th>
          <td class="p-2">
            {{ n(day.due) }}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
