<script setup lang="ts">
// Sales & POS → Sales (SALE-F28–F31; the old `erp-sales-list`): «Sales», the period (Today to begin
// with, 7 days, 30 days, All) counted from the hub's business day, the six figures of the period (only
// for whoever may see the reports) and the live `sale.sale.list` in a server-side DataTable — Date,
// Number, Customer, Payment, Status («<amount> left to refund» under a sale partly refunded), Total —,
// with search, the filters (status, payment, date, total; a date range replaces the period), table or
// cards and 50 a page. A row opens its document; «Document» and «Reprint» for everyone; «Void» and
// «Refund» by permission, only where they apply. Charges, voids and refunds come back through the
// stream by themselves: nothing here refetches. Everything the screen shows is the server's.
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState, formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, onMounted, ref, shallowRef, watch } from 'vue';

import DocumentModal from '../components/document/DocumentModal.vue';
import ReprintJob from '../components/document/ReprintJob.vue';
import { filterCount, filterQuery, hasDateRange, type SalesFilterValues } from '../components/sales/filters';
import { type DayBounds, type Period, PERIODS, periodBounds } from '../components/sales/period';
import RefundModal from '../components/sales/RefundModal.vue';
import SalesFilters from '../components/sales/SalesFilters.vue';
import SalesKpis from '../components/sales/SalesKpis.vue';
import { useBusinessDay } from '../components/sales/useBusinessDay';
import { useLiveList } from '../components/sales/useLiveList';
import { useServerTable } from '../components/sales/useServerTable';
import VoidSaleModal from '../components/sales/VoidSaleModal.vue';
import { useLocale, useT } from '../composables/useT';
import { formatMoney } from '../lib/format';
import type { SaleListIn, SaleRow } from '../operations';
import { saleTabs } from '../tabs';

const PERIOD_LABELS: Record<Period, string> = {
  today: 'sale.sales.period.today',
  week: 'sale.sales.period.week',
  month: 'sale.sales.period.month',
  all: 'sale.sales.period.all',
};

const session = useSession();
const canReports = computed(() => session.can('sale.view_reports'));
const canVoid = computed(() => session.can('sale.void_sale'));
const canRefund = computed(() => session.can('sale.refund_sale'));
const t = useT();
const locale = useLocale();

// ── The period: from the hub's business day; a date range of the filters replaces it ────────────
const day = useBusinessDay();
onMounted(() => void day.read());
const period = shallowRef<Period>('today');
const filters = ref<SalesFilterValues>({});

const bounds = computed<DayBounds>(() => {
  if (!hasDateRange(filters.value)) return periodBounds(period.value, day.today.value);
  const { date_from, date_to } = filterQuery(filters.value);
  return { ...(date_from ? { date_from } : {}), ...(date_to ? { date_to } : {}) };
});
/** The chip lit: none while a date range of the filters rules. */
const segmentValue = computed(() => (hasDateRange(filters.value) ? undefined : period.value));

function pickPeriod(event: CustomEvent<{ value?: unknown }>): void {
  const value = event.detail.value as Period;
  if (!PERIODS.includes(value)) return;
  period.value = value;
  if (hasDateRange(filters.value)) {
    const rest: Record<string, string | undefined> = { ...filters.value };
    delete rest.date_from;
    delete rest.date_to;
    filters.value = rest;
  }
  void day.read();
}

// ── The list ─────────────────────────────────────────────────────────────────────────────────────
const table = useServerTable({ sort: 'created_at', dir: 'desc' });
watch([filters, bounds], ([now]) => table.restart({ narrowed: filterCount(now) > 0 }));

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList('sale.sale.list', () => ({ ...filterQuery(filters.value), ...bounds.value, ...table.query.value }) as SaleListIn, () => table.windows.value);
table.followResult(result);

/** The failures that replace the list with a notice: the app is off here, or the person may not look. */
const blocked = computed(() => (error.value?.code === 'app_inactive' || error.value?.code === 'permission_denied' ? error.value.code : null));
/** A filter the server refused (a 422 of the list): said under the filter, the rows stay. */
const filterErrors = computed(() => error.value?.fields ?? {});
const tableError = computed(() => (status.value === 'error' && !Object.keys(filterErrors.value).length ? error.value?.message : undefined));

// ── Columns ──────────────────────────────────────────────────────────────────────────────────────
const dash = (value: unknown): string => (value === null || value === undefined || value === '' ? '—' : String(value));
const money = (cents: number): string => formatMoney(cents, locale.value);

const columns = computed<DataTableColumn<SaleRow>[]>(() => [
  { key: 'created_at', label: t('sale.sales.columns.date'), sortable: true, format: (_, row) => formatDateTime(row.created_at, locale.value) },
  { key: 'number', label: t('sale.sales.columns.number'), sortable: true, priority: 'high' },
  { key: 'customer_name', label: t('sale.sales.columns.customer'), sortable: true, format: dash },
  { key: 'payment_method_name', label: t('sale.sales.columns.payment'), sortable: true, format: dash },
  { key: 'status', label: t('sale.sales.columns.status'), sortable: true, cell: 'status', format: (_, row) => t(`sale.sales.status.${row.status}`) },
  { key: 'total', label: t('sale.sales.columns.total'), sortable: true, align: 'right', format: (_, row) => money(row.total) },
]);

/** A completed sale part of whose money already went back: what is still left to refund. */
const leftToRefund = (row: SaleRow): string | null =>
  row.status === 'completed' && row.refunded_total > 0 && row.refundable_total > 0 ? t('sale.sales.status.leftToRefund', { amount: money(row.refundable_total) }) : null;

// ── Row actions ──────────────────────────────────────────────────────────────────────────────────
/** Void: a completed ticket nothing went back from (a full invoice is corrected with a credit note). */
const voidable = (row: SaleRow): boolean => row.status === 'completed' && row.refunded_total === 0 && row.document_type === 'ticket';
/** Refund: a completed sale with money still to give back. */
const refundable = (row: SaleRow): boolean => row.status === 'completed' && row.refundable_total > 0;

const reprinting = shallowRef<string | null>(null);

const actions = computed<DataTableAction<SaleRow>[]>(() => [
  { id: 'document', label: t('sale.sales.actions.document'), icon: 'receipt-outline' },
  { id: 'reprint', label: t('sale.sales.actions.reprint'), icon: 'copy-outline', loading: (row) => reprinting.value === row.id },
  ...(canVoid.value ? [{ id: 'void', label: t('sale.sales.actions.void'), icon: 'ban-outline', color: 'danger', hidden: (row: SaleRow) => !voidable(row) }] : []),
  ...(canRefund.value
    ? [{ id: 'refund', label: t('sale.sales.actions.refund'), icon: 'lucide:rotate-ccw', color: 'warning', hidden: (row: SaleRow) => !refundable(row) }]
    : []),
]);

const docOpen = shallowRef(false);
const docSaleId = shallowRef<string | null>(null);
const voidOpen = shallowRef(false);
const voiding = shallowRef<SaleRow | null>(null);
const refundOpen = shallowRef(false);
const refunding = shallowRef<SaleRow | null>(null);

function openDocument(row: SaleRow): void {
  docSaleId.value = row.id;
  docOpen.value = true;
}

function onAction({ actionId, row }: { actionId: string; row: SaleRow }): void {
  if (actionId === 'document') openDocument(row);
  else if (actionId === 'reprint' && !reprinting.value) reprinting.value = row.id;
  else if (actionId === 'void' && canVoid.value && voidable(row)) {
    voiding.value = row;
    voidOpen.value = true;
  } else if (actionId === 'refund' && canRefund.value && refundable(row)) {
    refunding.value = row;
    refundOpen.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="$t('sale.title')"
    :tabs="saleTabs($t)"
    :tabs-label="$t('sale.tabs.label')"
  >
    <h2
      class="sales-page__title"
      data-testid="sales-title"
    >
      {{ $t('sale.sales.title') }}
    </h2>
    <ion-segment
      class="sales-page__range"
      data-testid="sales-range"
      :value="segmentValue"
      :aria-label="$t('sale.sales.period.label')"
      @ion-change="pickPeriod"
    >
      <ion-segment-button
        v-for="value in PERIODS"
        :key="value"
        :value="value"
        :data-testid="`sales-range-${value}`"
      >
        <ion-label>{{ $t(PERIOD_LABELS[value]) }}</ion-label>
      </ion-segment-button>
    </ion-segment>
    <InlineFeedback
      v-if="day.error.value"
      class="sales-page__notice"
      tone="warning"
      data-testid="sales-business-day-error"
    >
      {{ $t('sale.sales.businessDayError') }}
    </InlineFeedback>
    <SalesKpis
      v-if="canReports && !blocked"
      :bounds="bounds"
    />
    <InlineFeedback
      v-if="status === 'reconnecting'"
      class="sales-page__notice"
      tone="warning"
      data-testid="sales-reconnecting"
    >
      {{ $t('sale.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="blocked"
      tone="warning"
      :data-testid="blocked === 'app_inactive' ? 'sales-inactive' : 'sales-forbidden'"
      :heading="blocked === 'app_inactive' ? $t('sale.live.appInactive') : $t('sale.live.noPermission')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="table.search.value"
      testid="sales-table"
      server-side
      searchable
      row-clickable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :page-size-chooser="false"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: SaleRow) => row.number"
      :card-icon="() => 'receipt-outline'"
      :entity-label="{ one: $t('sale.sales.entity.one'), many: $t('sale.sales.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :actions="actions"
      :search-placeholder="$t('sale.sales.search')"
      :labels="{ loading: $t('sale.sales.loading'), loadError: $t('sale.sales.loadError'), retry: $t('sale.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @sort-change="table.setSort"
      @row-click="openDocument"
      @action="onAction"
      @retry="refresh()"
    >
      <template #filters>
        <SalesFilters
          v-model="filters"
          :field-errors="filterErrors"
        />
      </template>
      <template #status="{ row }">
        <span class="sales-page__status">
          <span>{{ $t(`sale.sales.status.${row.status}`) }}</span>
          <span
            v-if="leftToRefund(row)"
            class="sales-page__left"
            data-testid="sales-left-to-refund"
          >{{ leftToRefund(row) }}</span>
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="sales-empty"
          icon="receipt-outline"
          :heading="table.filtered.value ? $t('sale.sales.noMatches') : $t('sale.sales.empty')"
        />
      </template>
    </DataTable>
    <DocumentModal
      v-model:open="docOpen"
      :sale-id="docSaleId"
    />
    <ReprintJob
      v-if="reprinting"
      :key="reprinting"
      :sale-id="reprinting"
      @done="reprinting = null"
    />
    <VoidSaleModal
      v-if="canVoid"
      v-model:open="voidOpen"
      :sale="voiding"
    />
    <RefundModal
      v-if="canRefund"
      v-model:open="refundOpen"
      :sale="refunding"
    />
  </AppPage>
</template>

<style scoped>
.sales-page__title {
  margin: 0 0 0.75rem;
  font-size: 1.15rem;
}
.sales-page__range {
  margin: 0.25rem 0 0.75rem;
  max-width: 32rem;
}
.sales-page__notice {
  margin-bottom: 0.75rem;
}
.sales-page__status {
  display: inline-flex;
  flex-direction: column;
  line-height: 1.25;
}
/* «<amount> left to refund», under the status: smaller and muted, never broken across lines. */
.sales-page__left {
  font-size: 0.78em;
  color: var(--ion-color-medium-shade, #5f5f5f);
  white-space: nowrap;
}
</style>
