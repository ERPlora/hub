<script setup lang="ts">
// Tables → Zones (WORKBOOK «Pantallas · Zonas»; TABLE-F01, F06): the live `table.zone.list` in a
// server-side DataTable by Order — Name (with its colour), Tables, Free («free / total», right now), Order
// and Status (Active, Inactive) —, «Search zone…», column filters (name, colour, status), list or cards,
// 50 a page. «+» (whoever may add zones) and Edit (whoever may change them) open the zone's dialog; Delete
// (owner and admin) asks first, and is off for a zone with tables. Changes come back through the stream.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  StatusPill,
} from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import ZoneDeleteDialog from '../components/ZoneDeleteDialog.vue';
import ZoneFormModal from '../components/ZoneFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { ZoneColor, ZoneListIn, ZoneOut } from '../operations';
import { tableTabs } from '../tabs';

const COLORS: readonly ZoneColor[] = ['primary', 'secondary', 'tertiary', 'success', 'warning', 'danger', 'medium'];

const session = useSession();
const t = useT();
const canAdd = computed(() => session.can('table.add_zone'));
const canChange = computed(() => session.can('table.change_zone'));
const canDelete = computed(() => session.can('table.delete_zone'));

const table = useServerTable({ sort: 'sort_order' });
const filters = ref<DataTableFilters>({});
const query = computed<Partial<ZoneListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.name ? { name: f.name } : {}),
    ...(f.is_active ? { is_active: f.is_active === 'true' } : {}),
    ...(f.color ? { color: f.color as ZoneColor } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('table.zone.list', () => ({ ...query.value, ...table.query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<ZoneOut>[]>(() => [
  { key: 'name', label: t('table.zones.columns.name'), sortable: true, priority: 'high', cell: 'name', filter: { type: 'text' } },
  { key: 'table_count', label: t('table.zones.columns.tables'), sortable: true, align: 'right', format: (_, row) => String(row.table_count) },
  {
    key: 'available_count',
    label: t('table.zones.columns.available'),
    sortable: true,
    align: 'right',
    format: (_, row) => t('table.zones.availableOfTotal', { available: row.available_count, total: row.table_count }),
  },
  { key: 'sort_order', label: t('table.zones.columns.order'), sortable: true, align: 'right', format: (_, row) => String(row.sort_order) },
  {
    key: 'is_active',
    label: t('table.zones.columns.status'),
    sortable: true,
    cell: 'status',
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('table.zones.active') },
        { value: 'false', label: t('table.zones.inactive') },
      ],
    },
  },
  {
    key: 'color',
    label: t('table.zones.columns.color'),
    hidden: true,
    format: (_, row) => t(`table.color.${row.color}`),
    filter: { type: 'select', options: COLORS.map((value) => ({ value, label: t(`table.color.${value}`) })) },
  },
]);

const actions = computed<DataTableAction<ZoneOut>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('table.zones.actions.edit'), icon: 'create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('table.zones.actions.delete'), icon: 'trash-outline', color: 'danger' }] : []),
]);

const editing = ref<ZoneOut | null>(null);
const formOpen = ref(false);
const deleting = ref<ZoneOut | null>(null);
const deleteOpen = ref(false);

function openForm(zone: ZoneOut | null): void {
  editing.value = zone;
  formOpen.value = true;
}

function onAction({ actionId, row }: { actionId: string; row: ZoneOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'delete') {
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
      testid="table-zones"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="table-zones"
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
      :card-title="(row: ZoneOut) => row.name"
      :card-icon="() => 'layers-outline'"
      :entity-label="{ one: $t('table.zones.entity.one'), many: $t('table.zones.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('table.zones.loadError') : undefined"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('table.zones.search')"
      :labels="{ add: $t('table.zones.new'), loadError: $t('table.zones.loadError'), retry: $t('table.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="(row: ZoneOut) => canChange && openForm(row)"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #name="{ row }">
        <span class="table-zone-name">
          <span
            class="table-zone-name__dot"
            :style="{ background: `var(--ion-color-${row.color})` }"
            aria-hidden="true"
          />{{ row.name }}
        </span>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="row.is_active ? 'success' : 'neutral'"
          :label="row.is_active ? t('table.zones.active') : t('table.zones.inactive')"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="table-zones-empty"
          icon="layers-outline"
          :heading="table.filtered.value ? $t('table.noResults') : $t('table.zones.empty')"
          :message="table.filtered.value ? $t('table.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <ZoneFormModal
      v-model:open="formOpen"
      :zone="editing"
      variant="full"
      :can-delete="false"
    />
    <ZoneDeleteDialog
      v-if="deleting"
      v-model:open="deleteOpen"
      testid="table-zones-delete"
      :zone="deleting"
    />
  </AppPage>
</template>

<style scoped>
.table-zone-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.table-zone-name__dot {
  flex: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
</style>
