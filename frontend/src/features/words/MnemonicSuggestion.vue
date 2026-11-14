<script setup lang="ts">
import type { DictionaryRecord } from './dictionaryView'
import type { components } from '@/api/schema'
import { onScopeDispose, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import { useAuthStore } from '@/stores/auth'

const props = defineProps<{ target: DictionaryRecord, draft: string, disabled?: boolean }>()
const emit = defineEmits<{ accept: [text: string] }>()
const { t } = useI18n()
const auth = useAuthStore()
const text = ref('')
const error = ref('')
const pending = ref(false)
const replacing = ref(false)
let version = 0
let timer: ReturnType<typeof setTimeout> | undefined

function cancel() {
  version++
  clearTimeout(timer)
  pending.value = false
  replacing.value = false
  text.value = ''
  error.value = ''
}
watch(() => [props.target.id, props.target.table, auth.user?.id], cancel, { flush: 'sync' })
onScopeDispose(cancel)

function reason(value: string) {
  if (value === 'disabled')
    return 'mnemonics.unavailable'
  if (value === 'budget_exhausted')
    return 'mnemonics.budget'
  if (value === 'timeout')
    return 'mnemonics.timeout'
  if (value === 'stale_content' || value === 'invalid_scope')
    return 'mnemonics.stale'
  return 'mnemonics.provider'
}

async function suggest() {
  cancel()
  const started = version
  pending.value = true
  const target = { target_table: props.target.table, target_id: props.target.id }
  if (target.target_table !== 'lemma' && target.target_table !== 'lexeme' && target.target_table !== 'sense')
    return cancel()
  let polls = 0
  async function receive(result: components['schemas']['MnemonicSuggestion'] | undefined) {
    if (started !== version)
      return
    if (!result) {
      error.value = 'mnemonics.provider'
    }
    else if (result.status === 'ready') {
      text.value = result.text ?? ''
    }
    else if (result.status === 'unavailable') {
      error.value = reason(result.reason ?? '')
    }
    else if (result.job_id && ++polls <= 60) {
      const jobId = result.job_id
      timer = setTimeout(async () => {
        try {
          const response = await api.GET('/api/notes/suggestions/{job_id}', {
            params: {
              path: { job_id: jobId },
            },
          })
          await receive(response.data)
        }
        catch {
          if (started === version) {
            pending.value = false
            error.value = 'mnemonics.provider'
          }
        }
      }, 1000)
      return
    }
    else {
      error.value = 'mnemonics.timeout'
    }
    pending.value = false
  }
  try {
    const response = await api.POST('/api/notes/suggestions', {
      body: { target_table: target.target_table, target_id: target.target_id },
    })
    await receive(response.data)
  }
  catch {
    if (started === version) {
      pending.value = false
      error.value = 'mnemonics.provider'
    }
  }
}
function accept() {
  if (!text.value || props.disabled)
    return
  emit('accept', text.value)
  cancel()
}
</script>

<template>
  <section class="space-y-3" data-testid="mnemonic-suggestion" :aria-label="t('mnemonics.suggestion')">
    <p class="text-sm text-muted">
      {{ t('mnemonics.privacy') }}
    </p>
    <div class="flex flex-wrap gap-3">
      <NButton size="large" :loading="pending" :disabled="pending || disabled" data-testid="mnemonic-generate" @click="suggest">
        {{ t(error ? 'mnemonics.retry' : 'mnemonics.generate') }}
      </NButton>
      <NButton v-if="pending || text" size="large" data-testid="mnemonic-reject" @click="cancel">
        {{ t('word.cancel') }}
      </NButton>
    </div>
    <p v-if="pending" role="status">
      {{ t('mnemonics.loading') }}
    </p>
    <p v-if="error" role="alert">
      {{ t(error) }}
    </p>
    <template v-if="text">
      <p class="whitespace-pre-wrap break-words" data-testid="mnemonic-result">
        {{ text }}
      </p>
      <NButton size="large" :disabled="disabled" data-testid="mnemonic-accept" @click="draft.trim() ? replacing = true : accept()">
        {{ t('mnemonics.accept') }}
      </NButton>
    </template>
    <ConfirmAction
      :show="replacing" title-key="mnemonics.replace" content-key="mnemonics.replaceConfirm"
      @confirm="accept" @cancel="replacing = false"
    />
  </section>
</template>
