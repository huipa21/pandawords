<script setup lang="ts">
import type { DataTableColumns } from 'naive-ui'
import type { AdminUpdate, AdminUser } from './useAdminUsers'
import { computed, h, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ConfirmAction from '@/components/app/ConfirmAction.vue'
import EmptyState from '@/components/app/EmptyState.vue'
import ErrorState from '@/components/app/ErrorState.vue'
import PageHeader from '@/components/app/PageHeader.vue'
import { useAuthStore } from '@/stores/auth'
import CreateUserModal from './CreateUserModal.vue'
import TemporaryPasswordModal from './TemporaryPasswordModal.vue'
import { useAdminUsers } from './useAdminUsers'
import UserActions from './UserActions.vue'

const { t } = useI18n()
const auth = useAuthStore()
const {
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
} = useAdminUsers()
const creating = ref(false)
const pending = ref<{ user: AdminUser, body: AdminUpdate, titleKey: string } | null>(null)
const status = (user: AdminUser) => t(user.disabled ? 'admin.disabled' : 'admin.enabled')

function change(user: AdminUser, body: AdminUpdate, titleKey: string) {
  if (busy.value || loading.value)
    return
  if (user.id === auth.user?.id && (body.disabled === true || body.role === 'user'))
    return
  if (body.disabled === false) {
    void update(user, body)
    return
  }
  pending.value = { user, body, titleKey }
}

async function confirm() {
  if (pending.value && await update(pending.value.user, pending.value.body))
    pending.value = null
}

const columns = computed<DataTableColumns<AdminUser>>(() => [
  {
    title: t('auth.username'),
    key: 'username',
    className: 'break-all',
  },
  {
    title: t('admin.role'),
    key: 'role',
    render: user => t(`admin.roles.${user.role}`),
  },
  {
    title: t('admin.status'),
    key: 'disabled',
    render: status,
  },
  {
    title: t('admin.actions'),
    key: 'actions',
    render: user => h(UserActions, { user, busy: busy.value || loading.value, onChange: change }),
  },
])

function openCreate() {
  fieldError.value = ''
  creating.value = true
}
</script>

<template>
  <section class="mx-auto max-w-content space-y-6">
    <PageHeader :title="t('pages.users')" :subtitle="t('admin.protectionNotice')">
      <template #actions>
        <NSpin v-if="loading && loaded" size="small" :aria-label="t('common.loading')" />
        <NButton size="large" :disabled="busy || loading" @click="load()">
          {{ t('common.refresh') }}
        </NButton>
        <NButton size="large" type="primary" :disabled="busy || loading" @click="openCreate">
          {{ t('admin.create') }}
        </NButton>
      </template>
    </PageHeader>
    <div :aria-busy="loading">
      <div v-if="loading && !loaded" class="space-y-4" role="status" :aria-label="t('common.loading')">
        <NSkeleton v-for="row in 3" :key="row" text :repeat="3" />
      </div>
      <ErrorState v-if="loadError" :error="loadError" :loading="loading" @retry="retry" />
      <EmptyState v-else-if="loaded && !users.length" title-key="admin.empty">
        <template #action>
          <NButton size="large" type="primary" :disabled="busy || loading" @click="openCreate">
            {{ t('admin.create') }}
          </NButton>
        </template>
      </EmptyState>
      <template v-if="users.length">
        <div class="hidden lg:block">
          <NDataTable :columns="columns" :data="users" :row-key="(user: AdminUser) => user.id" />
        </div>
        <ul class="m-0 list-none space-y-4 p-0 lg:hidden" :aria-label="t('pages.users')">
          <li v-for="user in users" :key="user.id" class="space-y-3 border border-base rounded-lg bg-raised p-4">
            <h2 class="m-0 break-all text-lg font-semibold">
              {{ user.username }}
            </h2>
            <dl class="m-0 flex flex-wrap gap-4">
              <div>
                <dt class="text-sm text-muted">
                  {{ t('admin.role') }}
                </dt>
                <dd class="m-0">
                  {{ t(`admin.roles.${user.role}`) }}
                </dd>
              </div>
              <div>
                <dt class="text-sm text-muted">
                  {{ t('admin.status') }}
                </dt>
                <dd class="m-0">
                  {{ status(user) }}
                </dd>
              </div>
            </dl>
            <UserActions :user="user" :busy="busy || loading" @change="change" />
          </li>
        </ul>
      </template>
    </div>
    <nav v-if="loaded && total > pageSize" class="flex flex-wrap items-center justify-between gap-3" :aria-label="t('admin.pagination')">
      <NButton size="large" :disabled="page <= 1 || loading || busy" @click="load(page - 1)">
        {{ t('common.previous') }}
      </NButton>
      <span aria-live="polite">{{ t('admin.page', { page, pages: Math.ceil(total / pageSize), total }) }}</span>
      <NButton size="large" :disabled="page * pageSize >= total || loading || busy" @click="load(page + 1)">
        {{ t('common.next') }}
      </NButton>
    </nav>
    <CreateUserModal :show="creating" :busy="busy" :field-error="fieldError" :create="create" @close="creating = false" />
    <ConfirmAction
      :show="Boolean(pending)" :title-key="pending?.titleKey ?? 'common.confirm'"
      content-key="admin.confirmNotice" :params="{ username: pending?.user.username ?? '' }"
      :loading="busy" @confirm="confirm" @cancel="pending = null"
    />
    <TemporaryPasswordModal :password="creating || pending ? '' : password" :username="passwordUser" @close="clearPassword" />
  </section>
</template>
