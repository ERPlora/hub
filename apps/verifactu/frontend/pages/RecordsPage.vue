<script setup lang="ts">
// VeriFactu → Records (VERIFACTU-F16, F18; the old `erp-verifactu-records`): the live `verifactu.record.list` in a
// server-side DataTable — Seq, Invoice, Date, Type (Registration / Cancellation), F., Issuer, Total, Environment and
// Status (a coloured pill) —, the last sealed first, 50 a page, search «Search invoice, issuer or tax ID…» and the
// filters behind the table's funnel (Date, Type, Total, Environment and Status on their columns, then the
// invoice type; the total typed in euros). A row, or «View», opens its record;
// «Verify at the AEAT» opens the QR's link of the AEAT in a new tab. New, sent and answered records come back
// through the stream by themselves.
import {
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilterField,
  type DataTableFilters,
  DataTable,
  EmptyState,
  StatusPill,
} from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { backwardsDays, filterParams, filtersInUse, unreadableAmounts } from '../lib/filters';
import { formatDate, formatMoney } from '../lib/format';
import { ENVIRONMENTS, environmentTone, INVOICE_TYPES, RECORD_TYPES, STATUSES, statusTone } from '../lib/record';
import type { RecordListIn, RecordRowOut } from '../operations';
import { verifactuTabs } from '../tabs';

const router = useRouter();
const t = useT();
const locale = useLocale();

/** The table's filters (its funnel), as typed: the total in euros. A filter not in use is absent. */
const filters = ref<DataTableFilters>({});
const table = useServerTable('verifactu.record.list', {
  sort: 'created_at',
  dir: 'desc',
  maxSearch: 120,
  filters: (): Partial<RecordListIn> => filterParams(filters.value),
  // Only the filters that really apply narrow the list (a total it cannot read does not).
  narrowed: () => filtersInUse(filters.value) > 0,
});
const { data: result, status, error, refresh } = table;

const blocked = computed(() => blockingError(error.value));
/** What the server refused (a 422 of the list), a total it cannot read and a day «until» before its «from»,
 *  under each filter: the rows stay. */
const filterErrors = computed<Record<string, string>>(() => ({
  ...(error.value?.fields ?? {}),
  ...Object.fromEntries(unreadableAmounts(filters.value).map((name) => [name, t('verifactu.filters.amountInvalid')])),
  ...Object.fromEntries(backwardsDays(filters.value).map((name) => [name, t('verifactu.filters.dateOrder')])),
}));
const tableError = computed(() => (status.value === 'error' && !Object.keys(error.value?.fields ?? {}).length ? error.value?.message : undefined));
const options = (codes: readonly string[], label: (code: string) => string) => codes.map((value) => ({ value, label: label(value) }));

const columns = computed<DataTableColumn<RecordRowOut>[]>(() => [
  { key: 'sequence', label: t('verifactu.records.columns.seq'), sortable: true, width: 'minmax(3.5rem, 4.5rem)' },
  { key: 'invoice_number', label: t('verifactu.records.columns.invoice'), sortable: true, priority: 'high', width: 'minmax(9rem, 11rem)' },
  {
    key: 'issue_date',
    label: t('verifactu.records.columns.date'),
    sortable: true,
    width: 'minmax(7rem, 8rem)',
    format: (_, row) => formatDate(row.issue_date, locale.value),
    filter: { type: 'daterange', keys: ['issue_date_from', 'issue_date_to'] },
  },
  {
    key: 'record_type',
    label: t('verifactu.records.columns.type'),
    width: 'minmax(6rem, 8rem)',
    format: (_, row) => t(`verifactu.recordType.${row.record_type}`),
    filter: { type: 'select', options: options(RECORD_TYPES, (code) => t(`verifactu.recordType.${code}`)) },
  },
  { key: 'invoice_type', label: t('verifactu.records.columns.invoiceType'), sortable: true, width: 'minmax(3rem, 4rem)', format: (_, row) => row.invoice_type || '—' },
  { key: 'issuer_name', label: t('verifactu.records.columns.issuer'), sortable: true, priority: 'low', width: 'minmax(8rem, 1fr)' },
  {
    key: 'total_amount',
    label: t('verifactu.records.columns.total'),
    sortable: true,
    align: 'right',
    width: 'minmax(6rem, 7rem)',
    format: (_, row) => formatMoney(row.total_amount, locale.value),
    filter: { type: 'range', amount: true, keys: ['total_amount_from', 'total_amount_to'] },
  },
  {
    key: 'environment',
    label: t('verifactu.records.columns.environment'),
    sortable: true,
    cell: 'environment',
    width: 'minmax(7rem, 9rem)',
    format: (_, row) => t(`verifactu.env.${row.environment}`),
    filter: { type: 'select', options: options(ENVIRONMENTS, (code) => t(`verifactu.env.${code}`)) },
  },
  {
    key: 'status',
    label: t('verifactu.records.columns.status'),
    sortable: true,
    cell: 'status',
    width: 'minmax(7rem, 10rem)',
    format: (_, row) => t(`verifactu.status.${row.status}`),
    filter: { type: 'select', options: options(STATUSES, (code) => t(`verifactu.status.${code}`)) },
  },
]);

/** The invoice type filters apart: its column is «F.», too short to name a filter. Its codes are the AEAT's. */
const filterFields = computed<DataTableFilterField[]>(() => [
  { type: 'select', key: 'invoice_type', label: t('verifactu.filters.invoiceType'), options: options(INVOICE_TYPES, (code) => code) },
]);

const actions = computed<DataTableAction<RecordRowOut>[]>(() => [
  { id: 'view', label: t('verifactu.records.actions.view'), icon: 'lucide:eye', pinned: true },
  { id: 'verify', label: t('verifactu.records.actions.verify'), icon: 'ion:qr-code-outline' },
]);

function open(row: RecordRowOut): void {
  void router.push(`/verifactu/records/${row.id}`);
}

function onAction({ actionId, row }: { actionId: string; row: RecordRowOut }): void {
  if (actionId === 'view') open(row);
  else if (actionId === 'verify') window.open(row.qr_url, '_blank', 'noopener');
}
</script>

<template>
  <AppPage
    :title="$t('verifactu.records.title')"
    content-layout="fill"
    :tabs="verifactuTabs($t)"
    :tabs-label="$t('verifactu.tabs.label')"
  >
    <PageNotices
      testid="verifactu-records"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="verifactu-records"
      fill
      server-side
      searchable
      filterable
      :filter-fields="filterFields"
      :filter-errors="filterErrors"
      row-clickable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: RecordRowOut) => row.invoice_number"
      :card-icon="() => 'list-outline'"
      :entity-label="{ one: $t('verifactu.records.entity.one'), many: $t('verifactu.records.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :actions="actions"
      :search-placeholder="$t('verifactu.records.search')"
      :labels="{ loading: $t('verifactu.records.loading'), loadError: $t('verifactu.records.loadError'), retry: $t('verifactu.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="open"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="statusTone(row.status)"
          :label="$t(`verifactu.status.${row.status}`)"
          data-testid="verifactu-records-status"
        />
      </template>
      <template #environment="{ row }">
        <StatusPill
          size="sm"
          :tone="environmentTone(row.environment)"
          :label="$t(`verifactu.env.${row.environment}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="verifactu-records-empty"
          icon="list-outline"
          :heading="table.filtered.value ? $t('verifactu.records.noResults') : $t('verifactu.records.empty')"
          :message="table.filtered.value ? $t('verifactu.records.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
  </AppPage>
</template>
