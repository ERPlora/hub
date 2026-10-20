<script setup lang="ts">
// Services → «Bonos y paquetes» (WORKBOOK «Pantallas · Bonos y paquetes»; SERVICE-F12 to F19, F30): the
// live `service.package.list` in a server-side DataTable — Name, Discount, Closed price, Lines and
// Status (Active, Archived, Deleted) —, «Search package…», by order then name, 50 a page; the Status
// filter on Deleted is the view of the deleted vouchers somebody bought. Above, «Vouchers with no
// customer» for whoever may see them. A row offers Edit, Movements, Sold vouchers and Delete (with its
// confirmation); in the deleted view only Movements and Sold vouchers, and the row opens the sales.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  StatusPill,
} from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import GrantsSheet from '../components/GrantsSheet.vue';
import MovementsSheet from '../components/MovementsSheet.vue';
import OrphansSheet from '../components/OrphansSheet.vue';
import PackageFormModal from '../components/PackageFormModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMoney, formatPercentBp } from '../lib/format';
import type { PackageListIn, PackageOut, PackageStatus } from '../operations';
import { serviceTabs } from '../tabs';

const STATUSES: readonly PackageStatus[] = ['active', 'archived', 'deleted'];
const TONE: Record<PackageStatus, 'success' | 'neutral' | 'danger'> = { active: 'success', archived: 'neutral', deleted: 'danger' };

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('service.add_package'));
const canChange = computed(() => session.can('service.change_package'));
const canDelete = computed(() => session.can('service.delete_package'));
const canSeeSales = computed(() => session.can('service.view_package_balance'));
const canSeeOrphans = computed(() => session.can('service.view_orphan_grant'));

const table = useServerTable({ sort: 'sort_order' });
const filters = ref<DataTableFilters>({});
const deletedView = computed(() => filters.value.status === 'deleted');
const query = computed<Partial<PackageListIn>>(() => ({
  ...(filters.value.status ? { status: filters.value.status as PackageStatus } : {}),
  ...(filters.value.name ? { name: filters.value.name } : {}),
}));

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('service.package.list', () => ({ ...query.value, ...table.query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

function discount(row: PackageOut): string {
  if (row.discount_type === 'fixed') return row.discount_amount ? formatMoney(row.discount_amount, locale.value) : t('service.none');
  return row.discount_percent_bp ? formatPercentBp(row.discount_percent_bp, locale.value) : t('service.none');
}

const columns = computed<DataTableColumn<PackageOut>[]>(() => [
  { key: 'name', label: t('service.packages.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  { key: 'discount', label: t('service.packages.columns.discount'), sortable: false, align: 'right', format: (_, row) => discount(row) },
  {
    key: 'fixed_price',
    label: t('service.packages.columns.fixedPrice'),
    sortable: true,
    align: 'right',
    format: (_, row) => (row.fixed_price === null ? t('service.none') : formatMoney(row.fixed_price, locale.value)),
  },
  { key: 'item_count', label: t('service.packages.columns.lines'), sortable: true, align: 'right', format: (_, row) => String(row.item_count) },
  {
    key: 'status',
    label: t('service.packages.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`service.packages.status.${value}`) })) },
  },
]);

const actions = computed<DataTableAction<PackageOut>[]>(() => {
  const sales: DataTableAction<PackageOut>[] = canSeeSales.value
    ? [
        { id: 'movements', label: t('service.packages.actions.movements'), icon: 'time-outline' },
        { id: 'grants', label: t('service.packages.actions.grants'), icon: 'people-outline' },
      ]
    : [];
  if (deletedView.value) return sales;
  return [
    ...(canChange.value ? [{ id: 'edit', label: t('service.packages.actions.edit'), icon: 'create-outline' }] : []),
    ...sales,
    ...(canDelete.value ? [{ id: 'delete', label: t('service.packages.actions.delete'), icon: 'trash-outline', color: 'danger' }] : []),
  ];
});

// The form and the sheets
const editing = ref<PackageOut | null>(null);
const formOpen = ref(false);
const salesOf = ref<PackageOut | null>(null);
const salesOpen = ref(false);
const movementsOf = ref<PackageOut | null>(null);
const movementsOpen = ref(false);
const orphansOpen = ref(false);

function openForm(current: PackageOut | null): void {
  editing.value = current;
  formOpen.value = true;
}
function openSales(current: PackageOut): void {
  salesOf.value = current;
  salesOpen.value = true;
}
function openMovements(current: PackageOut): void {
  movementsOf.value = current;
  movementsOpen.value = true;
}

const remove = useCommand('service.package.delete');
const deleting = ref<PackageOut | null>(null);
const deleteOpen = ref(false);

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await remove.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

function onAction({ actionId, row }: { actionId: string; row: PackageOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'movements') openMovements(row);
  if (actionId === 'grants') openSales(row);
  if (actionId === 'delete') {
    remove.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}

function onRowClick(row: PackageOut): void {
  if (deletedView.value) {
    if (canSeeSales.value) openSales(row);
  } else if (canChange.value) openForm(row);
}
</script>

<template>
  <AppPage
    :title="$t('service.title')"
    content-layout="fill"
    :tabs="serviceTabs($t, { settings: session.can('service.manage_settings') })"
    :tabs-label="$t('service.tabs.label')"
  >
    <PageNotices
      testid="service-packages"
      :status="status"
      :error="error"
    />
    <div
      v-if="canSeeOrphans"
      class="service-packages__top"
    >
      <ion-button
        data-testid="service-packages-orphans-open"
        fill="outline"
        size="small"
        @click="orphansOpen = true"
      >
        {{ $t('service.packages.orphans') }}
      </ion-button>
    </div>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="service-packages"
      fill
      server-side
      searchable
      :filters="filters"
      filterable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: PackageOut) => row.name"
      :card-icon="() => 'ticket-outline'"
      :entity-label="{ one: $t('service.packages.entity.one'), many: $t('service.packages.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('service.packages.loadError') : undefined"
      :addable="canAdd && !deletedView"
      :row-clickable="deletedView ? canSeeSales : canChange"
      :actions="actions"
      :search-placeholder="$t('service.packages.search')"
      :labels="{ add: $t('service.packages.new'), loadError: $t('service.packages.loadError'), retry: $t('service.live.retry') }"
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
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="TONE[row.status]"
          :label="t(`service.packages.status.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="service-packages-empty"
          icon="ticket-outline"
          :heading="table.filtered.value ? $t('service.noResults') : $t('service.packages.empty')"
          :message="table.filtered.value ? $t('service.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <PackageFormModal
      v-model:open="formOpen"
      :pkg="editing"
    />
    <GrantsSheet
      v-if="salesOf"
      v-model:open="salesOpen"
      :pkg="salesOf"
    />
    <MovementsSheet
      v-if="movementsOf"
      v-model:open="movementsOpen"
      :pkg="movementsOf"
    />
    <OrphansSheet
      v-if="orphansOpen"
      v-model:open="orphansOpen"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="service-packages-delete"
      tone="danger"
      :title="t('service.packages.delete.title')"
      :message="deleting ? t('service.packages.delete.message', { name: deleting.name, count: deleting.item_count }) : ''"
      :confirm-label="t('service.packages.delete.confirm')"
      :cancel-label="t('service.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.service-packages__top {
  display: flex;
  justify-content: flex-end;
  padding: 0 0 8px;
}
</style>
