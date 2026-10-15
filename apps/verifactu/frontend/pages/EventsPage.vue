<script setup lang="ts">
// VeriFactu → Events (VERIFACTU-F31; the old `erp-verifactu-events`): «Audit events», the live
// `verifactu.event.list` in a server-side DataTable — When (the business's clock), Severity, Type and Message, which
// the server composes in the reader's language —, the newest first, search «Search type or message…» (the words that
// show, in Spanish or English) and the filters of type, severity and day. Unlike the old screen it follows itself.
import { type DataTableColumn, DataTable, EmptyState, formatDateTime, StatusPill } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import ListFilters from '../components/ListFilters.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { filterCount, filterQuery, type FilterValues } from '../components/filters';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { severityTone } from '../lib/record';
import type { EventListIn, EventOut } from '../operations';
import { verifactuTabs } from '../tabs';

const router = useRouter();
const t = useT();
const locale = useLocale();

const filters = ref<FilterValues>({});
const table = useServerTable('verifactu.event.list', {
  sort: 'created_at',
  dir: 'desc',
  maxSearch: 120,
  filters: (): Partial<EventListIn> => filterQuery(filters.value),
  narrowed: () => filterCount(filters.value) > 0,
});
const { data: result, status, error, refresh } = table;
const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const columns = computed<DataTableColumn<EventOut>[]>(() => [
  { key: 'created_at', label: t('verifactu.events.columns.when'), sortable: true, width: 'minmax(9rem, 11rem)', format: (_, row) => formatDateTime(row.created_at, locale.value) },
  { key: 'severity', label: t('verifactu.events.columns.severity'), sortable: true, cell: 'severity', width: 'minmax(6rem, 8rem)', format: (_, row) => t(`verifactu.severity.${row.severity}`) },
  { key: 'kind', label: t('verifactu.events.columns.type'), sortable: true, width: 'minmax(8rem, 11rem)', format: (_, row) => t(`verifactu.kind.${row.kind}`) },
  { key: 'message', label: t('verifactu.events.columns.message'), priority: 'high', width: 'minmax(14rem, 1fr)' },
]);

function open(row: EventOut): void {
  if (row.record_id) void router.push(`/verifactu/records/${row.record_id}`);
}
</script>

<template>
  <AppPage
    :title="$t('verifactu.events.title')"
    :tabs="verifactuTabs($t)"
    :tabs-label="$t('verifactu.tabs.label')"
  >
    <PageNotices
      testid="verifactu-events"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="verifactu-events"
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: EventOut) => $t(`verifactu.kind.${row.kind}`)"
      :card-icon="() => 'time-outline'"
      :entity-label="{ one: $t('verifactu.events.entity.one'), many: $t('verifactu.events.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :search-placeholder="$t('verifactu.events.search')"
      :labels="{ loading: $t('verifactu.events.loading'), loadError: $t('verifactu.events.loadError'), retry: $t('verifactu.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="open"
      @retry="refresh()"
    >
      <template #filters>
        <ListFilters
          v-model="filters"
          list="events"
        />
      </template>
      <template #severity="{ row }">
        <StatusPill
          size="sm"
          :tone="severityTone(row.severity)"
          :label="$t(`verifactu.severity.${row.severity}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="verifactu-events-empty"
          icon="time-outline"
          :heading="table.filtered.value ? $t('verifactu.records.noResults') : $t('verifactu.events.empty')"
        />
      </template>
    </DataTable>
  </AppPage>
</template>
