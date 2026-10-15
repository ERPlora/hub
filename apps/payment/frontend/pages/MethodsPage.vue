<script setup lang="ts">
// Payments → Methods (WORKBOOK «Pantallas · Métodos»; PAYMENT-F01, F08): the accounts the business pays
// from, live (`payment.method.list`) in a server-side DataTable — Name, Type, Account and Status —,
// «Search method…», filters by type and state, by name, 50 a page. «New method» and a row (or its Edit)
// open the form for whoever records payments; Deactivate takes a method out of «New payment» and
// Activate brings it back. A method is never deleted. Changes come back through the stream.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import MethodFormModal from '../components/MethodFormModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { MethodListIn, MethodOut, MethodType } from '../operations';
import { paymentTabs } from '../tabs';

const TYPES: readonly MethodType[] = ['cash', 'transfer', 'card', 'sepa', 'check', 'other'];

const session = useSession();
const t = useT();
const canManage = computed(() => session.can('payment.add_payment'));

const table = useServerTable({ sort: 'name' });
const filters = ref<DataTableFilters>({});

/** The table's filters as the query takes them: the state as a boolean. */
const query = computed<Partial<MethodListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.method_type ? { method_type: f.method_type as MethodType } : {}),
    ...(f.is_active ? { is_active: f.is_active === 'true' } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'payment.method.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<MethodOut>[]>(() => [
  { key: 'name', label: t('payment.methods.columns.name'), sortable: true, priority: 'high' },
  {
    key: 'method_type',
    label: t('payment.methods.columns.type'),
    sortable: true,
    format: (_, row) => t(`payment.types.${row.method_type}`),
    filter: { type: 'select', options: TYPES.map((value) => ({ value, label: t(`payment.types.${value}`) })) },
  },
  { key: 'bank_account_ref', label: t('payment.methods.columns.account'), sortable: true },
  {
    key: 'is_active',
    label: t('payment.methods.columns.status'),
    sortable: true,
    cell: 'state',
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('payment.methods.state.active') },
        { value: 'false', label: t('payment.methods.state.inactive') },
      ],
    },
  },
]);

const actions = computed<DataTableAction<MethodOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('payment.methods.actions.edit'), icon: 'create-outline' },
        {
          id: 'deactivate',
          label: t('payment.methods.actions.deactivate'),
          icon: 'ban-outline',
          color: 'danger',
          loading: (row) => busy.value === row.id,
          hidden: (row) => !row.is_active,
        },
        {
          id: 'activate',
          label: t('payment.methods.actions.activate'),
          icon: 'checkmark-circle-outline',
          color: 'success',
          loading: (row) => busy.value === row.id,
          hidden: (row) => row.is_active,
        },
      ]
    : [],
);

// The form
const editing = ref<MethodOut | null>(null);
const formOpen = ref(false);
function openForm(method: MethodOut | null): void {
  editing.value = method;
  formOpen.value = true;
}

// Row actions
const deactivate = useCommand('payment.method.deactivate');
const activate = useCommand('payment.method.activate');
const rowError = ref<ApiError | null>(null);
/** The row whose command is running: a second tap meanwhile does nothing (one command per tap). */
const busy = ref<string | null>(null);

async function onAction({ actionId, row }: { actionId: string; row: MethodOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'edit') {
    openForm(row);
    return;
  }
  const command = actionId === 'deactivate' ? deactivate : actionId === 'activate' ? activate : null;
  if (!command || busy.value) return;
  busy.value = row.id;
  try {
    await command.run({ id: row.id });
  } catch {
    rowError.value = command.error.value;
  } finally {
    busy.value = null;
  }
}

function onRowClick(row: MethodOut): void {
  if (canManage.value) openForm(row);
}
</script>

<template>
  <AppPage
    :title="$t('payment.title')"
    :tabs="paymentTabs($t)"
    :tabs-label="$t('payment.tabs.label')"
  >
    <PageNotices
      testid="payment-methods"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="payment-methods-row-error"
      :heading="t('payment.methods.actionError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="payment-methods"
      server-side
      searchable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: MethodOut) => row.name"
      :card-icon="() => 'wallet-outline'"
      :entity-label="{ one: $t('payment.methods.entity.one'), many: $t('payment.methods.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('payment.methods.loadError') : undefined"
      :addable="canManage"
      :row-clickable="canManage"
      :actions="actions"
      :search-placeholder="$t('payment.methods.search')"
      :labels="{ add: $t('payment.methods.new'), loadError: $t('payment.methods.loadError'), retry: $t('payment.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="onRowClick"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #state="{ row }">
        <StatusPill
          size="sm"
          :tone="row.is_active ? 'success' : 'neutral'"
          :label="row.is_active ? t('payment.methods.state.active') : t('payment.methods.state.inactive')"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="payment-methods-empty"
          icon="wallet-outline"
          :heading="table.filtered.value ? $t('payment.noResults') : $t('payment.methods.empty')"
          :message="table.filtered.value ? $t('payment.noResultsMessage') : $t('payment.methods.emptyMessage')"
        />
      </template>
    </DataTable>
    <MethodFormModal
      v-model:open="formOpen"
      :method="editing"
    />
  </AppPage>
</template>
