<script setup lang="ts">
// Employees › Roles: erplora.com's roles and, after them, the business's own. A basic role is given when a person is
// invited on erplora.com and changed there; who manages the roles makes one of the business's own from any, and adjusts
// or deletes it. A row opens what the role allows. The link leaves the Hub by `openExternalLink` (the installed app opens
// nothing on a `_blank` link) and is never offered in the Google Play copy (`managementOffered`).
import { ConfirmDialog, DataTable, type DataTableAction, type DataTableColumn, StatusPill } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { openExternalLink, toastSuccess, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { type HubHome, readJsonBlock } from '../lib/embedded';
import { useBaseI18n } from '../lib/i18n';
import { managementOffered } from '../lib/management';
import { roleName } from '../lib/people';
import type { HubRoleRow } from '../operations/people';
import NewRoleModal from './NewRoleModal.vue';

const { t, locale } = useBaseI18n();
const session = useSession();
const router = useRouter();
const admin = computed(() => session.can('base.administer_hub'));
const manages = computed(() => session.can('base.manage_roles'));
const membersUrl = readJsonBlock<HubHome>('hub-home')?.members_url ?? '';
const offered = managementOffered();

const { data, status, refresh } = useLive('base.role.list', {});

const rows = computed<HubRoleRow[]>(() => data.value?.roles ?? []);
const failed = computed(() => status.value === 'error' && data.value === undefined);
const number = (n: number) => new Intl.NumberFormat(locale.value).format(n);
const openRole = (key: string) => void router.push(`/employees/roles/${key}`);

const columns = computed<DataTableColumn<HubRoleRow>[]>(() => [
  { key: 'key', label: t('base.roles.columns.role'), format: (_, row) => roleName(row, t), width: 'minmax(10rem,2fr)' },
  { key: 'origin', label: t('base.roles.columns.origin'), cell: 'origin', width: '12rem', sortable: false },
  { key: 'members', label: t('base.roles.columns.members'), cell: 'members', align: 'right', width: '7rem' },
  { key: 'permissions', label: t('base.roles.columns.permissions'), cell: 'permissions', align: 'right', width: '7rem', priority: 'low' },
]);

const basic = (row: HubRoleRow) => row.origin === 'basic';
const actions = computed<DataTableAction<HubRoleRow>[]>(() =>
  manages.value
    ? [
        { id: 'duplicate', label: t('base.roles.duplicate'), icon: 'ion:copy-outline', pinned: true },
        { id: 'edit', label: t('base.roles.edit'), icon: 'ion:create-outline', menuOnly: true, hidden: (row) => basic(row) || row.mine },
        { id: 'delete', label: t('base.roles.delete'), icon: 'ion:trash-outline', color: 'danger', menuOnly: true, hidden: basic },
      ]
    : [],
);

function onAction({ actionId, row }: { actionId: string; row: HubRoleRow }): void {
  if (actionId === 'duplicate') startFrom(row.key);
  if (actionId === 'edit') openRole(row.key);
  if (actionId === 'delete') ask(row);
}

// ── A new role, from another ──
const creating = ref(false);
const from = ref('');

function startFrom(key: string): void {
  from.value = key;
  creating.value = true;
}

// ── Deleting one of the business's own ──
const remove = useCommand('base.role.delete');
const asking = ref(false);
const deleting = ref<HubRoleRow>();

function ask(row: HubRoleRow): void {
  remove.error.value = null;
  deleting.value = row;
  asking.value = true;
}

async function confirmDelete(): Promise<void> {
  const row = deleting.value;
  if (!row) return;
  try {
    await remove.run({ role: row.key });
  } catch {
    return; // The question shows the refusal.
  }
  asking.value = false;
  toastSuccess(t('base.roles.remove.done', { name: row.label }));
}
</script>

<template>
  <section class="roles">
    <header class="roles-head">
      <p class="roles-intro">
        {{ t('base.roles.intro') }}
      </p>
      <a
        v-if="admin && membersUrl && offered"
        class="roles-change"
        data-testid="roles-change"
        :href="membersUrl"
        target="_blank"
        rel="noopener"
        @click="openExternalLink(membersUrl, $event)"
      >{{ t('base.roles.change') }}</a>
    </header>
    <DataTable
      testid="roles"
      row-key="key"
      :columns="columns"
      :rows="rows"
      :page-size="10"
      :page-size-options="[]"
      :views="['table', 'cards']"
      :card-title="(row: HubRoleRow) => roleName(row, t)"
      card-title-column="key"
      :search-keys="['label']"
      :search-placeholder="t('base.roles.search')"
      :empty-message="t('base.roles.empty')"
      :loading="data === undefined && !failed"
      :error="failed ? t('base.roles.error') : undefined"
      :addable="manages"
      :labels="{ add: t('base.roles.new') }"
      :actions="actions"
      row-clickable
      @row-click="(row: HubRoleRow) => openRole(row.key)"
      @add="startFrom('hub_employee')"
      @action="onAction"
      @retry="refresh()"
    >
      <template #origin="{ row }">
        <StatusPill
          size="sm"
          tone="neutral"
          :label="t(`base.roles.${(row as HubRoleRow).origin}`)"
        />
        <StatusPill
          v-if="(row as HubRoleRow).to_review"
          size="sm"
          tone="warning"
          data-testid="roles-to-review"
          :label="t('base.roles.toReview')"
        />
      </template>
      <template #members="{ row }">
        <span data-testid="roles-members">{{ number((row as HubRoleRow).members) }}</span>
      </template>
      <template #permissions="{ row }">
        <span data-testid="roles-permissions">{{ number((row as HubRoleRow).permissions) }}</span>
      </template>
    </DataTable>
    <NewRoleModal
      v-if="manages"
      v-model:open="creating"
      :roles="rows"
      :from="from"
      @created="openRole"
    />
    <ConfirmDialog
      v-model:open="asking"
      testid="role-delete"
      tone="danger"
      :title="t('base.roles.remove.title')"
      :message="t('base.roles.remove.message', { name: deleting?.label ?? '' })"
      :confirm-label="t('base.roles.delete')"
      confirm-icon="ion:trash-outline"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
    />
  </section>
</template>

<style scoped>
.roles {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.roles-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.roles-intro {
  flex: 1 1 20rem;
  margin: 0;
  color: var(--ion-color-medium-shade, #555);
  font-size: 0.875rem;
}

.roles-change {
  padding: 8px 14px;
  border: 1px solid var(--ion-color-primary);
  border-radius: var(--ep-radius, 12px);
  color: var(--ion-color-primary);
  font-size: 0.875rem;
  font-weight: 600;
  text-decoration: none;
}
</style>
