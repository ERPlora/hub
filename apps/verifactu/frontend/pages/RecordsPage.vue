<script setup lang="ts">
// VeriFactu → Records (VERIFACTU-F16, F18; the old `erp-verifactu-records`): the live `verifactu.record.list` in a
// server-side DataTable — Seq, Invoice, Date, Type (Registration / Cancellation), F., Issuer, Total, Environment and
// Status (a coloured pill) —, the last sealed first, 50 a page, search «Search invoice, issuer or tax ID…» and the
// filters panel (status, type, invoice type, environment, dates, total). A row, or «View», opens its record;
// «Verify at the AEAT» opens the QR's link of the AEAT in a new tab. New, sent and answered records come back
// through the stream by themselves.
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import ListFilters from '../components/ListFilters.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { filterCount, filterQuery, type FilterValues } from '../components/filters';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney } from '../lib/format';
import { environmentTone, statusTone } from '../lib/record';
import type { RecordListIn, RecordRowOut } from '../operations';
import { verifactuTabs } from '../tabs';

const router = useRouter();
const t = useT();
const locale = useLocale();

const filters = ref<FilterValues>({});
const table = useServerTable('verifactu.record.list', {
  sort: 'created_at',
  dir: 'desc',
  maxSearch: 120,
  filters: (): Partial<RecordListIn> => filterQuery(filters.value),
  narrowed: () => filterCount(filters.value) > 0,
});
const { data: result, status, error, refresh } = table;

const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const columns = computed<DataTableColumn<RecordRowOut>[]>(() => [
  { key: 'sequence', label: t('verifactu.records.columns.seq'), sortable: true, width: 'minmax(3.5rem, 4.5rem)' },
  { key: 'invoice_number', label: t('verifactu.records.columns.invoice'), sortable: true, priority: 'high', width: 'minmax(9rem, 11rem)' },
  { key: 'issue_date', label: t('verifactu.records.columns.date'), sortable: true, width: 'minmax(7rem, 8rem)', format: (_, row) => formatDate(row.issue_date, locale.value) },
  { key: 'record_type', label: t('verifactu.records.columns.type'), width: 'minmax(6rem, 8rem)', format: (_, row) => t(`verifactu.recordType.${row.record_type}`) },
  { key: 'invoice_type', label: t('verifactu.records.columns.invoiceType'), sortable: true, width: 'minmax(3rem, 4rem)', format: (_, row) => row.invoice_type || '—' },
  { key: 'issuer_name', label: t('verifactu.records.columns.issuer'), sortable: true, priority: 'low', width: 'minmax(8rem, 1fr)' },
  { key: 'total_amount', label: t('verifactu.records.columns.total'), sortable: true, align: 'right', width: 'minmax(6rem, 7rem)', format: (_, row) => formatMoney(row.total_amount, locale.value) },
  { key: 'environment', label: t('verifactu.records.columns.environment'), sortable: true, cell: 'environment', width: 'minmax(7rem, 9rem)', format: (_, row) => t(`verifactu.env.${row.environment}`) },
  { key: 'status', label: t('verifactu.records.columns.status'), sortable: true, cell: 'status', width: 'minmax(7rem, 10rem)', format: (_, row) => t(`verifactu.status.${row.status}`) },
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
      testid="verifactu-records"
      fill
      server-side
      searchable
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
      <template #filters>
        <ListFilters
          v-model="filters"
          list="records"
        />
      </template>
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
