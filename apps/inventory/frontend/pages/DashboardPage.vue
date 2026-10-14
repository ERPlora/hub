<script setup lang="ts">
// Inventory → Dashboard (WORKBOOK «Panel», INVENTORY-F17), the old `erp-inventory-dashboard`: the
// figures of `inventory.stock.get_summary` (the first four lead to Products; the value is at cost,
// with a note when tracked articles have no cost) and «Low stock products», five a page, from the one
// with less. Both follow the stream: a sale, a count or a new product anywhere re-runs them on the
// server; nothing here refetches.
import { type DataTableColumn, DataTable, InlineFeedback } from '@erplora/ui/components';
import { type InputOf, type OutputOf, useLive } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { computed } from 'vue';

import KpiTile from '../components/KpiTile.vue';
import { useInventoryTabs } from '../composables/useInventoryTabs';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { formatCount, formatMoney, formatQuantity } from '../lib/format';

type LowRow = OutputOf<'inventory.product.list_low_stock'>['rows'][number];

const PRODUCTS = '/inventory/products';

const { t, locale } = useT();
const tabs = useInventoryTabs();

const { data: summary, status: summaryStatus, error: summaryError, refresh } = useLive('inventory.stock.get_summary', {});

const table = useServerTable<NonNullable<InputOf<'inventory.product.list_low_stock'>['sort']>>({ sort: 'stock', pageSize: 5 });
const { data: lowStock, status: lowStatus, error: lowError } = useLiveList('inventory.product.list_low_stock', () => table.params.value, table.windows);
table.followResult(lowStock);

const inactive = computed(() => summaryError.value?.code === 'app_inactive' || lowError.value?.code === 'app_inactive');
const reconnecting = computed(() => summaryStatus.value === 'reconnecting' || lowStatus.value === 'reconnecting');

const kpis = computed(() => {
  const s = summary.value;
  if (!s) return [];
  const count = (n: number) => formatCount(n, locale.value);
  return [
    { id: 'tracked', label: t('inventory.dashboard.tracked'), value: count(s.products_tracked), icon: 'ion:cube-outline', to: PRODUCTS },
    { id: 'in-stock', label: t('inventory.dashboard.inStock'), value: count(s.products_in_stock), icon: 'ion:checkmark-circle-outline', to: PRODUCTS },
    {
      id: 'out-of-stock',
      label: t('inventory.dashboard.outOfStock'),
      value: count(s.products_out_of_stock),
      icon: 'ion:close-outline',
      to: PRODUCTS,
      tone: s.products_out_of_stock > 0 ? ('danger' as const) : ('neutral' as const),
    },
    {
      id: 'low-stock',
      label: t('inventory.dashboard.lowStock'),
      value: count(s.products_low_stock),
      icon: 'ion:warning-outline',
      to: PRODUCTS,
      tone: s.products_low_stock > 0 ? ('warning' as const) : ('neutral' as const),
    },
    {
      id: 'value',
      label: t('inventory.dashboard.value'),
      value: formatMoney(s.stock_value, locale.value),
      icon: 'ion:wallet-outline',
      note: t('inventory.dashboard.valueAtCost'),
    },
  ];
});

// Each cell has its own hook: the figures are read exactly, never out of the whole row.
const columns = computed<DataTableColumn<LowRow>[]>(() => [
  { key: 'name', label: t('inventory.common.name'), priority: 'high', cell: 'name' },
  { key: 'sku', label: t('inventory.common.sku') },
  { key: 'stock', label: t('inventory.common.stock'), align: 'right', cell: 'stock' },
  { key: 'low_stock_threshold', label: t('inventory.common.threshold'), align: 'right', cell: 'threshold' },
]);
</script>

<template>
  <AppPage
    :title="$t('inventory.title')"
    :tabs="tabs"
    :tabs-label="$t('inventory.tabs.label')"
  >
    <InlineFeedback
      v-if="reconnecting"
      tone="warning"
      data-testid="inventory-dashboard-reconnecting"
    >
      {{ $t('inventory.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="inventory-dashboard-inactive"
      :heading="$t('inventory.live.appInactive')"
    >
      {{ (summaryError ?? lowError)?.message }}
    </InlineFeedback>
    <div
      v-else
      class="inventory-dashboard"
    >
      <p
        v-if="!summary && summaryStatus === 'loading'"
        class="inventory-dashboard__state"
        data-testid="inventory-dashboard-loading"
      >
        {{ $t('inventory.common.loading') }}
      </p>
      <InlineFeedback
        v-if="summaryStatus === 'error'"
        tone="danger"
        data-testid="inventory-dashboard-stats-error"
      >
        {{ $t('inventory.dashboard.statsError') }}
      </InlineFeedback>
      <div
        v-if="summary"
        class="inventory-dashboard__kpis"
        role="group"
        :aria-label="$t('inventory.dashboard.figures')"
      >
        <KpiTile
          v-for="kpi in kpis"
          :key="kpi.id"
          :testid="`inventory-dashboard-kpi-${kpi.id}`"
          :label="kpi.label"
          :value="kpi.value"
          :icon="kpi.icon"
          :to="kpi.to"
          :note="kpi.note"
          :tone="kpi.tone ?? 'neutral'"
        />
      </div>
      <p
        v-if="summary && summary.products_without_cost > 0"
        class="inventory-dashboard__note"
        data-testid="inventory-dashboard-without-cost"
      >
        {{ $t('inventory.dashboard.withoutCost', summary.products_without_cost) }}
      </p>

      <section class="inventory-dashboard__low">
        <h2>{{ $t('inventory.dashboard.lowStockTitle') }}</h2>
        <DataTable
          testid="inventory-dashboard-low-stock"
          server-side
          :column-picker="false"
          :page-size-chooser="false"
          :page-size-options="[]"
          :rows="lowStock?.rows ?? []"
          :total="lowStock?.total ?? 0"
          :page="table.page.value"
          :page-size="table.pageSize.value"
          :views="['table', 'cards']"
          :card-title="(row: LowRow) => row.name"
          :columns="columns"
          :loading="lowStatus === 'loading'"
          :error="lowStatus === 'error' ? lowError?.message : undefined"
          :empty-message="$t('inventory.dashboard.lowStockEmpty')"
          :labels="{ loadError: $t('inventory.dashboard.lowStockLoadError'), retry: $t('inventory.live.retry') }"
          @page-change="table.goToPage"
          @load-more="table.loadMore"
          @retry="refresh()"
        >
          <template #name="{ row }">
            <span data-testid="inventory-low-stock-name">{{ row.name }}</span>
          </template>
          <template #stock="{ row }">
            <span data-testid="inventory-low-stock-stock">{{ formatQuantity(row.stock, locale) }}</span>
          </template>
          <template #threshold="{ row }">
            <span data-testid="inventory-low-stock-threshold">{{ formatQuantity(row.low_stock_threshold, locale) }}</span>
          </template>
        </DataTable>
      </section>
    </div>
  </AppPage>
</template>

<style scoped>
.inventory-dashboard__kpis {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.75rem;
  margin: 0 0 1rem;
}

.inventory-dashboard__state {
  margin: 0 0 1rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}

.inventory-dashboard__note {
  margin: 0 0 1rem;
  font-size: 0.85rem;
  color: var(--ion-color-warning-shade, var(--ion-color-warning));
}

.inventory-dashboard__low h2 {
  margin: 0 0 0.75rem;
  font-size: 1rem;
}
</style>
