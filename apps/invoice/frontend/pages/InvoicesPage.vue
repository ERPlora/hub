<script setup lang="ts">
// Invoicing → Invoices (INVOICE-F16, F19, F03, F08; the old `erp-invoice-list`): the live
// `invoice.invoice.list` in a server-side DataTable — Number, Customer, Total, Status, Date, Type —, the
// last issued first (the old list sat on the internal id), 50 a page, search «Search invoices…» (number,
// customer's name or tax ID) and the filters panel (status, type, series, source, dates, total); table or
// cards (on a phone, cards titled by the number). A row, or «View», opens its invoice. «Mark as paid» only
// on an issued invoice and for whoever may issue; «Rectify» only where it applies and for whoever may
// rectify; «+» opens «New manual invoice». A refused row action is said above the table. Issued, rectified
// and paid invoices come back through the stream by themselves: nothing here refetches.
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, shallowRef } from 'vue';
import { useRouter } from 'vue-router';

import InvoiceCreateModal from '../components/InvoiceCreateModal.vue';
import InvoiceFilters from '../components/InvoiceFilters.vue';
import { filterCount, filterQuery, type InvoiceFilterValues } from '../components/filters';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import RectifyModal from '../components/RectifyModal.vue';
import { useMarkPaid } from '../composables/useMarkPaid';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney } from '../lib/format';
import { statusTone } from '../lib/invoice';
import type { InvoiceListIn, InvoiceRowOut } from '../operations';
import { invoiceTabs } from '../tabs';

const session = useSession();
const canAdd = computed(() => session.can('invoice.add_invoice'));
const canRectify = computed(() => session.can('invoice.rectify_invoice'));
const router = useRouter();
const t = useT();
const locale = useLocale();

const filters = ref<InvoiceFilterValues>({});
const table = useServerTable('invoice.invoice.list', {
  sort: 'issued_at',
  dir: 'desc',
  maxSearch: 120,
  filters: (): Partial<InvoiceListIn> => filterQuery(filters.value),
  narrowed: () => filterCount(filters.value) > 0,
});
const { data: result, status, error, refresh } = table;

const blocked = computed(() => blockingError(error.value));
/** A filter the server refused (a 422 of the list): said under the filter, the rows stay. */
const filterErrors = computed(() => error.value?.fields ?? {});
const tableError = computed(() => (status.value === 'error' && !Object.keys(filterErrors.value).length ? error.value?.message : undefined));

const dash = (value: unknown): string => (value === null || value === undefined || value === '' ? '—' : String(value));

const columns = computed<DataTableColumn<InvoiceRowOut>[]>(() => [
  { key: 'number', label: t('invoice.list.columns.number'), sortable: true, priority: 'high', width: 'minmax(9rem, 11rem)' },
  { key: 'customer_name', label: t('invoice.list.columns.customer'), sortable: true, format: dash, width: 'minmax(10rem, 1fr)' },
  {
    key: 'total_amount',
    label: t('invoice.list.columns.total'),
    sortable: true,
    align: 'right',
    width: 'minmax(7rem, 8rem)',
    format: (_, row) => formatMoney(row.total_amount, locale.value),
  },
  { key: 'status', label: t('invoice.list.columns.status'), sortable: true, cell: 'status', width: 'minmax(7rem, 9rem)', format: (_, row) => t(`invoice.status.${row.status}`) },
  { key: 'issue_date', label: t('invoice.list.columns.date'), sortable: true, width: 'minmax(7rem, 9rem)', format: (_, row) => formatDate(row.issue_date, locale.value) },
  {
    key: 'invoice_type',
    label: t('invoice.list.columns.type'),
    sortable: true,
    priority: 'low',
    width: 'minmax(6rem, 8rem)',
    format: (_, row) => t(`invoice.types.${row.invoice_type}`),
  },
]);

const paid = useMarkPaid();

const actions = computed<DataTableAction<InvoiceRowOut>[]>(() => [
  { id: 'view', label: t('invoice.list.actions.view'), icon: 'lucide:eye', pinned: true },
  ...(canAdd.value
    ? [
        {
          id: 'paid',
          label: t('invoice.list.actions.markPaid'),
          icon: 'ion:checkmark-circle-outline',
          color: 'success',
          hidden: (row: InvoiceRowOut) => !row.can_mark_paid,
          loading: (row: InvoiceRowOut) => paid.pending.value === row.id,
        },
      ]
    : []),
  ...(canRectify.value
    ? [{ id: 'rectify', label: t('invoice.list.actions.rectify'), icon: 'ion:arrow-undo-outline', color: 'danger', hidden: (row: InvoiceRowOut) => !row.can_rectify }]
    : []),
]);

const creating = shallowRef(false);
const rectifyOpen = shallowRef(false);
const rectifying = shallowRef<InvoiceRowOut | null>(null);

function open(row: InvoiceRowOut): void {
  void router.push(`/invoice/invoices/${row.id}`);
}

function onAction({ actionId, row }: { actionId: string; row: InvoiceRowOut }): void {
  if (actionId === 'view') open(row);
  else if (actionId === 'paid' && canAdd.value && row.can_mark_paid) void paid.mark(row);
  else if (actionId === 'rectify' && canRectify.value && row.can_rectify) {
    rectifying.value = row;
    rectifyOpen.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="$t('invoice.title')"
    content-layout="fill"
    :tabs="invoiceTabs($t)"
    :tabs-label="$t('invoice.tabs.label')"
  >
    <PageNotices
      testid="invoice-list"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="paid.refused.value"
      class="invoice-list__notice"
      tone="danger"
      data-testid="invoice-action-error"
    >
      {{ paid.refused.value }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="invoice-list"
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
      :card-title="(row: InvoiceRowOut) => row.number"
      :card-icon="() => 'receipt-outline'"
      :entity-label="{ one: $t('invoice.list.entity.one'), many: $t('invoice.list.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canAdd"
      :actions="actions"
      :search-placeholder="$t('invoice.list.search')"
      :labels="{ add: $t('invoice.list.add'), loading: $t('invoice.list.loading'), loadError: $t('invoice.list.loadError'), retry: $t('invoice.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="open"
      @action="onAction"
      @add="creating = true"
      @retry="refresh()"
    >
      <template #filters>
        <InvoiceFilters
          v-model="filters"
          :field-errors="filterErrors"
        />
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="statusTone(row.status)"
          :label="$t(`invoice.status.${row.status}`)"
          data-testid="invoice-list-status"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="invoice-list-empty"
          icon="receipt-outline"
          :heading="table.filtered.value ? $t('invoice.list.noResults') : $t('invoice.list.empty')"
          :message="table.filtered.value ? $t('invoice.list.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <InvoiceCreateModal
      v-if="canAdd"
      v-model:open="creating"
    />
    <RectifyModal
      v-if="canRectify"
      v-model:open="rectifyOpen"
      :invoice="rectifying"
    />
  </AppPage>
</template>

<style scoped>
.invoice-list__notice {
  margin-bottom: 0.75rem;
}
</style>
