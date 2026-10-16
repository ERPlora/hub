<script setup lang="ts">
// Inventory → Movements (WORKBOOK «Movimientos», INVENTORY-F16), the old `erp-inventory-movements`:
// the stock ledger, never edited, live (`inventory.movement.list`) in a server-side DataTable — Date,
// Name, SKU, Type, Quantity with its sign, Balance, Reason and Reference —, most recent first, 50 a
// page, search, filters by Type and Reference and sort by Date, Type, Quantity or Balance. Every
// movement made anywhere (a reception, a count, a sale) re-runs the query on the server.
import { type DataTableColumn, DataTable, formatDateTime, InlineFeedback } from '@erplora/ui/components';
import type { InputOf, OutputOf } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useInventoryTabs } from '../composables/useInventoryTabs';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { formatQuantity, formatSignedQuantity } from '../lib/format';

type Row = OutputOf<'inventory.movement.list'>['rows'][number];
type MovementType = Row['movement_type'];

const TYPES: MovementType[] = ['initial', 'reception', 'sale', 'void', 'count', 'write_off', 'refund'];

const { t, locale } = useT();
const tabs = useInventoryTabs();

const table = useServerTable<NonNullable<InputOf<'inventory.movement.list'>['sort']>>({ sort: '-created_at' });
const typeFilter = ref<MovementType | 'all'>('all');
const referenceFilter = ref('');
watch([typeFilter, referenceFilter], ([type, reference]) => table.restart({ narrowed: type !== 'all' || reference.trim() !== '' }));

const { data: result, status, error, refresh } = useLiveList(
  'inventory.movement.list',
  () => ({
    ...(typeFilter.value !== 'all' ? { movement_type: typeFilter.value } : {}),
    ...(referenceFilter.value.trim() ? { reference: referenceFilter.value.trim() } : {}),
    ...table.params.value,
  }),
  table.windows,
);
table.followResult(result);

const inactive = computed(() => error.value?.code === 'app_inactive');

function filterByType(event: CustomEvent<{ value?: unknown }>): void {
  const value = event.detail.value;
  typeFilter.value = TYPES.includes(value as MovementType) ? (value as MovementType) : 'all';
}

function filterByReference(event: CustomEvent<{ value?: unknown }>): void {
  referenceFilter.value = typeof event.detail.value === 'string' ? event.detail.value : '';
}

const TYPE_KEYS: Record<MovementType, string> = {
  initial: 'inventory.movements.types.initial',
  reception: 'inventory.movements.types.reception',
  sale: 'inventory.movements.types.sale',
  void: 'inventory.movements.types.void',
  count: 'inventory.movements.types.count',
  write_off: 'inventory.movements.types.write_off',
  refund: 'inventory.movements.types.refund',
};
const typeLabel = (type: MovementType): string => t(TYPE_KEYS[type]);

const columns = computed<DataTableColumn<Row>[]>(() => [
  {
    key: 'created_at',
    label: t('inventory.movements.columns.date'),
    sortable: true,
    width: 'minmax(6.75rem,0.9fr)',
    format: (value) => formatDateTime(String(value), locale.value),
  },
  { key: 'product_name', label: t('inventory.movements.columns.name'), priority: 'high', width: 'minmax(7.5rem,3.1fr)' },
  { key: 'sku', label: t('inventory.movements.columns.sku'), width: 'minmax(4.5rem,0.8fr)' },
  { key: 'movement_type', label: t('inventory.movements.columns.type'), sortable: true, cell: 'type', width: 'minmax(5.5rem,0.8fr)' },
  {
    key: 'qty',
    label: t('inventory.movements.columns.qty'),
    sortable: true,
    align: 'right',
    width: '5.25rem',
    format: (value) => formatSignedQuantity(String(value), locale.value),
  },
  {
    key: 'stock_after',
    label: t('inventory.movements.columns.balance'),
    sortable: true,
    align: 'right',
    width: '4.75rem',
    format: (value) => formatQuantity(String(value), locale.value),
  },
  { key: 'reason', label: t('inventory.movements.columns.reason'), priority: 'low', width: 'minmax(3.25rem,1fr)' },
  { key: 'reference', label: t('inventory.movements.columns.reference'), priority: 'low', width: 'minmax(4.75rem,1.25fr)' },
]);
</script>

<template>
  <AppPage
    :title="$t('inventory.title')"
    content-layout="fill"
    :tabs="tabs"
    :tabs-label="$t('inventory.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="inventory-movements-reconnecting"
    >
      {{ $t('inventory.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="inventory-movements-inactive"
      :heading="$t('inventory.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="table.search.value"
      testid="inventory-movements"
      fill
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sortKey.value"
      :sort-dir="table.sortDir.value"
      :views="['table', 'cards']"
      :card-title="(row: Row) => row.product_name"
      :columns="columns"
      :loading="status === 'loading'"
      :error="status === 'error' ? error?.message : undefined"
      :search-placeholder="$t('inventory.movements.search')"
      :empty-message="table.filtered.value ? $t('inventory.movements.noMatches') : $t('inventory.movements.empty')"
      :labels="{ loadError: $t('inventory.movements.loadError'), retry: $t('inventory.live.retry') }"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @retry="refresh()"
    >
      <template #filters>
        <ion-select
          data-testid="inventory-movements-type-filter"
          interface="popover"
          :aria-label="$t('inventory.movements.filters.type')"
          :value="typeFilter"
          @ion-change="filterByType"
        >
          <ion-select-option value="all">
            {{ $t('inventory.movements.filters.all') }}
          </ion-select-option>
          <ion-select-option
            v-for="type in TYPES"
            :key="type"
            :value="type"
          >
            {{ typeLabel(type) }}
          </ion-select-option>
        </ion-select>
        <ion-input
          class="inventory-movements__reference"
          data-testid="inventory-movements-reference-filter"
          :aria-label="$t('inventory.movements.filters.reference')"
          :placeholder="$t('inventory.movements.filters.reference')"
          :value="referenceFilter"
          :debounce="300"
          :clear-input="true"
          @ion-input="filterByReference"
        />
      </template>
      <template #type="{ row }">
        <span data-testid="inventory-movement-type">{{ typeLabel(row.movement_type) }}</span>
      </template>
    </DataTable>
  </AppPage>
</template>

<style scoped>
.inventory-movements__reference {
  /* Boxed like the toolbar's selects, so it reads as a filter and not as loose text. */
  max-width: 12rem;
  min-height: 40px;
  border: 1px solid var(--ion-color-step-250, #c8c7cc);
  border-radius: 8px;
  --padding-start: 10px;
  --padding-end: 6px;
}
</style>
