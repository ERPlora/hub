<script setup lang="ts">
// Menus (WORKBOOK «Pantallas · Menús»; COMBO-F01 to F04): the live `combo.combo.list` in a server-side
// DataTable — Name, Closed price (in the business's currency), How it is sold, On sale, Order —, «Search a menu…», filters by name,
// how it is sold and on sale, by order then name, 50 a page, table or cards. With the right to manage,
// «+» opens «New menu» and each row «Edit details» and «Withdraw» (after its confirmation); the new or
// changed row arrives through the stream. Tapping a row opens the menu's builder.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
} from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import ItemImage from '../../../../base/frontend/components/ItemImage.vue';
import MenuFormModal from '../components/MenuFormModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMoney, useBusinessMoney } from '../lib/format';
import type { ComboListIn, ComboOut, SupplyKind } from '../operations';

const session = useSession();
const router = useRouter();
const t = useT();
const locale = useLocale();
/** The business's currency (its country's), a bare figure until it answers: never a euro by default. */
const money = useBusinessMoney();
const canManage = computed(() => session.can('combo.manage'));

const table = useServerTable({ sort: 'sort_order' });
const filters = ref<DataTableFilters>({});

/** The filters as the query takes them: «On sale» is a yes/no. */
const query = computed<Partial<ComboListIn>>(() => ({
  ...(filters.value.name ? { name: filters.value.name } : {}),
  ...(filters.value.supply_kind ? { supply_kind: filters.value.supply_kind as SupplyKind } : {}),
  ...(filters.value.is_active ? { is_active: filters.value.is_active === 'true' } : {}),
}));

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('combo.combo.list', () => ({ ...query.value, ...table.query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const yesNo = computed(() => [
  { value: 'true', label: t('combo.yes') },
  { value: 'false', label: t('combo.no') },
]);

const columns = computed<DataTableColumn<ComboOut>[]>(() => [
  // COMBO-F14: the menu's photo thumbnail before its name (its initials without one), in the list and on the cards.
  { key: 'photo', label: t('combo.menus.photo'), sortable: false, cell: 'photo', width: '4rem' },
  { key: 'name', label: t('combo.menus.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  { key: 'price', label: t('combo.menus.columns.price'), sortable: true, align: 'right', format: (_, row) => formatMoney(row.price, locale.value, money.value) },
  {
    key: 'supply_kind',
    label: t('combo.menus.columns.supply'),
    sortable: true,
    format: (_, row) => t(`combo.supply.${row.supply_kind}`),
    filter: {
      type: 'select',
      options: [
        { value: 'service', label: t('combo.supply.service') },
        { value: 'goods', label: t('combo.supply.goods') },
      ],
    },
  },
  {
    key: 'is_active',
    label: t('combo.menus.columns.active'),
    sortable: true,
    format: (_, row) => (row.is_active ? t('combo.yes') : t('combo.no')),
    filter: { type: 'select', options: yesNo.value },
  },
  { key: 'sort_order', label: t('combo.menus.columns.order'), sortable: true, align: 'right', priority: 'low', format: (_, row) => String(row.sort_order) },
]);

const actions = computed<DataTableAction<ComboOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('combo.menus.actions.edit'), icon: 'create-outline' },
        { id: 'delete', label: t('combo.menus.actions.delete'), icon: 'trash-outline', color: 'danger' },
      ]
    : [],
);

// The form and the confirmation
const editing = ref<ComboOut | null>(null);
const formOpen = ref(false);

function openForm(current: ComboOut | null): void {
  editing.value = current;
  formOpen.value = true;
}

const remove = useCommand('combo.combo.delete');
const deleting = ref<ComboOut | null>(null);
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

function onAction({ actionId, row }: { actionId: string; row: ComboOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'delete') {
    remove.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}

function onRowClick(row: ComboOut): void {
  void router.push(`/combo/menus/${row.id}`);
}
</script>

<template>
  <AppPage
    :title="$t('combo.title')"
    content-layout="fill"
  >
    <PageNotices
      testid="combo-menus"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="combo-menus"
      fill
      server-side
      searchable
      row-clickable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: ComboOut) => row.name"
      :card-icon="() => 'layers-outline'"
      :entity-label="{ one: $t('combo.menus.entity.one'), many: $t('combo.menus.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('combo.menus.loadError') : undefined"
      :addable="canManage"
      :actions="actions"
      :search-placeholder="$t('combo.menus.search')"
      :labels="{ add: $t('combo.menus.add'), loadError: $t('combo.menus.loadError'), retry: $t('combo.live.retry') }"
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
      <template #photo="{ row }">
        <ItemImage
          class="combo-menu-photo"
          :data-testid="`combo-menu-photo-${row.id}`"
          :src="row.image_url"
          :name="row.name"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="combo-menus-empty"
          icon="layers-outline"
          :heading="table.filtered.value ? $t('combo.noResults') : $t('combo.menus.empty')"
          :message="table.filtered.value ? $t('combo.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <MenuFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :combo="editing"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="combo-menus-delete"
      tone="danger"
      :title="t('combo.menus.delete.title')"
      :message="deleting ? t('combo.menus.delete.message', { name: deleting.name }) : ''"
      :confirm-label="t('combo.menus.delete.confirm')"
      :cancel-label="t('combo.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.combo-menu-photo {
  width: 40px;
  height: 40px;
  font-size: 0.85rem;
  border-radius: 8px;
}
</style>
