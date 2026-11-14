import type { FormInst } from 'naive-ui'
import type { Ref } from 'vue'
import { useMessage } from 'naive-ui'
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AuthRequestError, errorKey } from './errors'

export function useAuthForm(form: Readonly<Ref<FormInst | null>>) {
  const { t, te } = useI18n()
  const message = useMessage()
  const loading = ref(false)
  const errors = reactive<Record<string, string>>({})
  const localizedError = (code: string) => t(te(errorKey(code))
    ? errorKey(code)
    : 'errors.generic')

  async function submit(action: () => Promise<void>, fields: string[]) {
    if (loading.value)
      return
    for (const field of Object.keys(errors))
      delete errors[field]
    try {
      await form.value?.validate()
    }
    catch {
      return
    }
    loading.value = true
    try {
      await action()
    }
    catch (error) {
      const detail = error instanceof AuthRequestError
        ? error.error
        : { code: 'generic', field: null }
      const text = localizedError(detail.code)
      if (detail.field && fields.includes(detail.field))
        errors[detail.field] = text
      else
        message.error(text)
    }
    finally {
      loading.value = false
    }
  }
  return { t, loading, errors, submit }
}
