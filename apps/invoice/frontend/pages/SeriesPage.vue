<script setup lang="ts">
// Invoicing → Series (INVOICE-F12, F13; the old `erp-invoice-settings`): the intro, then the live
// `invoice.series.list` in a server-side DataTable — Code, Name, Type, Year, Prefix, Format (empty reads
// PREFIX-YYYY-NNNNNN), Current no., Active and Default —, this year's first, search «Search code, name…»;
// under 1280 px it opens in cards (the nine columns do not fit). «+» opens «New numbering series» and «Edit»
// (or the row) «Edit series <code>», for whoever keeps the series; anyone else only looks. A new series
// starts on the business's year (`invoice.numbering.status`). Changes come back through the stream.
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, shallowRef } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import SeriesFormModal from '../components/SeriesFormModal.vue';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { SeriesOut } from '../operations';
import { invoiceTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('invoice.manage_series'));
const t = useT();

const table = useServerTable('invoice.series.list', { sort: 'year', dir: 'desc', maxSearch: 120 });
const { data: result, status, error, refresh } = table;
const numbering = useLive('invoice.numbering.status', () => ({}));

const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const yesNo = (value: unknown): string => (value ? t('invoice.yes') : t('invoice.no'));

const columns = computed<DataTableColumn<SeriesOut>[]>(() => [
  { key: 'code', label: t('invoice.series.columns.code'), sortable: true, priority: 'high', width: 'minmax(4.5rem, 1fr)' },
  { key: 'name', label: t('invoice.series.columns.name'), sortable: true, width: 'minmax(9rem, 3fr)', format: (_, row) => row.display_name || '—' },
  { key: 'invoice_type', label: t('invoice.series.columns.type'), sortable: true, width: 'minmax(7rem, 1.5fr)', format: (_, row) => t(`invoice.typeNames.${row.invoice_type}`) },
  { key: 'year', label: t('invoice.series.columns.year'), sortable: true, align: 'right', width: '3.5rem' },
  { key: 'prefix', label: t('invoice.series.columns.prefix'), sortable: true, width: 'minmax(4.5rem, 1fr)', format: (value) => (value ? String(value) : '—') },
  { key: 'format', label: t('invoice.series.columns.format'), width: 'minmax(9.75rem, 2fr)', format: (value) => (value ? String(value) : t('invoice.series.defaultFormat')) },
  { key: 'current_number', label: t('invoice.series.columns.number'), sortable: true, align: 'right', width: '6.5rem' },
  { key: 'is_active', label: t('invoice.series.columns.active'), sortable: true, width: '4.5rem', format: yesNo },
  { key: 'is_default', label: t('invoice.series.columns.default'), sortable: true, width: '4.75rem', format: (value) => (value ? t('invoice.yes') : '—') },
]);

const actions = computed<DataTableAction<SeriesOut>[]>(() =>
  canManage.value ? [{ id: 'edit', label: t('invoice.series.actions.edit'), icon: 'ion:create-outline', pinned: true }] : [],
);

const formOpen = shallowRef(false);
const editing = shallowRef<SeriesOut | null>(null);
const year = computed(() => numbering.data.value?.fiscal_year ?? new Date().getFullYear());

function add(): void {
  editing.value = null;
  formOpen.value = true;
}

function edit(row: SeriesOut): void {
  if (!canManage.value) return;
  editing.value = row;
  formOpen.value = true;
}

function onAction({ actionId, row }: { actionId: string; row: SeriesOut }): void {
  if (actionId === 'edit') edit(row);
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
      testid="invoice-series"
      :status="status"
      :error="error"
    />
    <p
      class="invoice-series__intro"
      data-testid="invoice-series-intro"
    >
      {{ $t('invoice.series.intro') }}
    </p>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="invoice-series"
      fill
      server-side
      searchable
      :row-clickable="canManage"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-breakpoint="1280"
      :card-title="(row: SeriesOut) => `${row.code} · ${row.year}`"
      :card-icon="() => 'layers-outline'"
      :entity-label="{ one: $t('invoice.series.entity.one'), many: $t('invoice.series.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canManage"
      :actions="actions"
      :search-placeholder="$t('invoice.series.search')"
      :labels="{ add: $t('invoice.series.add'), loading: $t('invoice.series.loading'), loadError: $t('invoice.series.loadError'), retry: $t('invoice.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="edit"
      @action="onAction"
      @add="add"
      @retry="refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="invoice-series-empty"
          icon="layers-outline"
          :heading="table.filtered.value ? $t('invoice.series.noResults') : $t('invoice.series.empty')"
        />
      </template>
    </DataTable>
    <SeriesFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :series="editing"
      :year="year"
    />
  </AppPage>
</template>

<style scoped>
.invoice-series__intro {
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.85rem;
  margin: 0 0 0.75rem;
  max-width: 60ch;
  line-height: 1.45;
}
</style>
