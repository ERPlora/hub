<script setup lang="ts">
// Tables → Tables (WORKBOOK «Pantallas · Mesas»; TABLE-F02, F04, F05): the live `table.table.list` in a
// server-side DataTable in natural order (2 before 10: the server sorts, so pages are cut right) —
// Number, Name, Zone, Capacity and Status (right now) —, «Search table…» (number and name), column filters
// (zone, capacity, status), list or cards, 50 a page. «+» (whoever may add tables) opens «New table»;
// Edit and a row (whoever may change them) open «Edit table»; Delete (owner and admin) asks first.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  StatusPill,
} from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import TableFormModal from '../components/TableFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { STATUS_TONE } from '../lib/floor';
import type { TableListIn, TableOut, TableStatus } from '../operations';
import { tableTabs } from '../tabs';

const STATUSES: readonly TableStatus[] = ['available', 'occupied', 'reserved', 'blocked'];

const session = useSession();
const t = useT();
const canAdd = computed(() => session.can('table.add_table'));
const canChange = computed(() => session.can('table.change_table'));
const canDelete = computed(() => session.can('table.delete_table'));

const table = useServerTable({ sort: 'number' });
const filters = ref<DataTableFilters>({});
const whole = (text: string | undefined): number | undefined => (text && /^\d+$/.test(text.trim()) ? Number(text.trim()) : undefined);
const query = computed<Partial<TableListIn>>(() => {
  const f = filters.value;
  const out: Partial<TableListIn> = {
    ...(f.number ? { number: f.number } : {}),
    ...(f.name ? { name: f.name } : {}),
    ...(f.zone_id ? { zone_id: f.zone_id } : {}),
    ...(f.status ? { status: f.status as TableStatus } : {}),
  };
  const min = whole(f.capacity_from);
  const max = whole(f.capacity_to);
  if (min !== undefined) out.capacity_min = min;
  if (max !== undefined) out.capacity_max = max;
  return out;
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('table.table.list', () => ({ ...query.value, ...table.query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

// The zones of the filter and of the form (a room has a handful).
const { data: zoneList } = useLive('table.zone.list', { limit: 100 });
const zones = computed(() => zoneList.value?.rows ?? []);

const columns = computed<DataTableColumn<TableOut>[]>(() => [
  { key: 'number', label: t('table.tables.columns.number'), sortable: true, priority: 'high', filter: { type: 'text' } },
  { key: 'name', label: t('table.tables.columns.name'), sortable: true, format: (_, row) => row.name || t('table.none'), filter: { type: 'text' } },
  {
    key: 'zone_name',
    label: t('table.tables.columns.zone'),
    sortable: true,
    format: (_, row) => row.zone_name ?? t('table.form.noZone'),
    filter: { type: 'select', key: 'zone_id', options: zones.value.map((zone) => ({ value: zone.id, label: zone.name })) },
  },
  { key: 'capacity', label: t('table.tables.columns.capacity'), sortable: true, align: 'right', format: (_, row) => String(row.capacity), filter: { type: 'range' } },
  {
    key: 'status',
    label: t('table.tables.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`table.status.${value}`) })) },
  },
]);

const actions = computed<DataTableAction<TableOut>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('table.tables.actions.edit'), icon: 'create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('table.tables.actions.delete'), icon: 'trash-outline', color: 'danger' }] : []),
]);

const editing = ref<TableOut | null>(null);
const formOpen = ref(false);
function openForm(row: TableOut | null): void {
  editing.value = row;
  formOpen.value = true;
}

const removal = useCommand('table.table.delete');
const deleting = ref<TableOut | null>(null);
const deleteOpen = ref(false);

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await removal.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

function onAction({ actionId, row }: { actionId: string; row: TableOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'delete') {
    removal.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="$t('table.title')"
    content-layout="fill"
    :tabs="tableTabs($t, { settings: session.can('table.manage_settings') })"
    :tabs-label="$t('table.tabs.label')"
  >
    <PageNotices
      testid="table-tables"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="table-tables"
      fill
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
      :card-title="(row: TableOut) => t('table.tableLabel', { number: row.number })"
      :card-icon="() => 'grid-outline'"
      :entity-label="{ one: $t('table.tables.entity.one'), many: $t('table.tables.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('table.tables.loadError') : undefined"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('table.tables.search')"
      :labels="{ add: $t('table.tables.new'), loadError: $t('table.tables.loadError'), retry: $t('table.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="(row: TableOut) => canChange && openForm(row)"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="STATUS_TONE[row.status]"
          :label="t(`table.status.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="table-tables-empty"
          icon="grid-outline"
          :heading="table.filtered.value ? $t('table.noResults') : $t('table.tables.empty')"
          :message="table.filtered.value ? $t('table.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <TableFormModal
      v-model:open="formOpen"
      :table="editing"
      :zones="zones"
      :can-delete="canDelete"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="table-tables-delete"
      tone="danger"
      :title="deleting ? t('table.form.deleteTitle', { number: deleting.number }) : ''"
      :message="t('table.form.deleteMessage')"
      :confirm-label="t('table.form.deleteConfirm')"
      :cancel-label="t('table.cancel')"
      :pending="removal.pending.value"
      :error="removal.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>
