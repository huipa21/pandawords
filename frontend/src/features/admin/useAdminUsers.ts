import type { components } from '@/api/schema'
import { useMessage } from 'naive-ui'
import { onMounted, onScopeDispose, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@/api/client'
import { normalizeApiError } from '@/api/errors'

export type AdminUser = components['schemas']['UserRead']
export type AdminCreate = components['schemas']['AdminUserCreate']
export type AdminUpdate = components['schemas']['AdminUserUpdate']

function createUser(body: AdminCreate) {
  return api.POST('/api/admin/users', { body })
}

export function useAdminUsers() {
  const { t, te } = useI18n()
  const message = useMessage()
  const users = ref<AdminUser[]>([])
  const page = ref(1)
  const requestedPage = ref(1)
  const pageSize = ref(20)
  const total = ref(0)
  const loaded = ref(false)
  const loading = ref(false)
  const busy = ref(false)
  const loadError = ref('')
  const fieldError = ref('')
  const password = ref('')
  const passwordUser = ref('')
  let request = 0
  let disposed = false

  function errorText(error: unknown, status: number) {
    const key = `errors.${normalizeApiError(error, status).code.replaceAll('.', '_')}`
    return t(te(key)
      ? key
      : 'errors.generic')
  }

  function clearPassword() {
    password.value = ''
    passwordUser.value = ''
  }

  async function load(target = page.value) {
    const current = ++request
    requestedPage.value = target
    loading.value = true
    loadError.value = ''
    try {
      const result = await api.GET('/api/admin/users', {
        params: {
          query: { page: target, page_size: pageSize.value },
        },
      })
      if (current !== request || disposed)
        return
      if (!result.data) {
        loadError.value = errorText(result.error, result.response.status)
        return
      }
      users.value = result.data.items
      page.value = result.data.page
      pageSize.value = result.data.page_size
      total.value = result.data.total
      loaded.value = true
    }
    catch {
      if (current === request && !disposed)
        loadError.value = t('errors.transport')
    }
    finally {
      if (current === request && !disposed)
        loading.value = false
    }
  }

  async function mutate(action: () => ReturnType<typeof createUser>, create = false) {
    if (busy.value)
      return false
    busy.value = true
    fieldError.value = ''
    clearPassword()
    try {
      const result = await action()
      if (disposed)
        return false
      if (!result.data) {
        const detail = normalizeApiError(result.error, result.response.status)
        const text = errorText(detail, result.response.status)
        if (create && detail.field === 'username')
          fieldError.value = text
        else
          message.error(text)
        return false
      }
      const data = result.data
      if (data.temporary_password) {
        password.value = data.temporary_password
        passwordUser.value = data.user.username
      }
      message.success(t('admin.saved'))
      if (create) {
        await load(1)
      }
      else {
        users.value = users.value.map(user => user.id === data.user.id
          ? data.user
          : user)
      }
      return true
    }
    catch {
      if (!disposed)
        message.error(t('errors.transport'))
      return false
    }
    finally {
      busy.value = false
    }
  }

  const create = (body: AdminCreate) => mutate(
    () => createUser(body),
    true,
  )
  const update = (user: AdminUser, body: AdminUpdate) => mutate(
    () => api.PATCH('/api/admin/users/{id}', {
      params: {
        path: { id: user.id },
      },
      body,
    }),
  )
  const retry = () => load(requestedPage.value)

  onMounted(() => load())
  onScopeDispose(() => {
    disposed = true
    request++
    clearPassword()
  })
  return {
    users,
    page,
    pageSize,
    total,
    loaded,
    loading,
    busy,
    loadError,
    fieldError,
    password,
    passwordUser,
    load,
    retry,
    create,
    update,
    clearPassword,
  }
}
