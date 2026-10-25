<script setup lang="ts">
// The counts of a session (CASH_REGISTER-F06, F11; the old detail's «Counts» table) in a server-side
// DataTable, newest first, 50 a page, table or cards (titled by their date and time): When, Count type,
// Total counted and Notes. They re-run by themselves when a count is recorded.
import { type DataTableColumn, DataTable, EmptyState, formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMoney, useCurrency } from '../lib/money';
import type { CountOut } from '../operations';

const props = defineProps<{ sessionId: string }>();

const t = useT();
const locale = useLocale();
const currency = useCurrency();

const table = useServerTable('cash_register.count.list', {
  sort: 'counted_at',
  dir: 'desc',
  maxSearch: 0,
  filters: () => ({ session_id: props.sessionId }),
});
const { data: result, status, error, refresh } = table;

const tableError = computed(() => (status.value === 'error' ? (error.value?.message ?? t('cash_register.detail.loadError')) : undefined));
const when = (row: CountOut): string => formatDateTime(row.counted_at, locale.value);

const columns = computed<DataTableColumn<CountOut>[]>(() => [
  { key: 'counted_at', label: t('cash_register.counts.columns.when'), sortable: true, width: 'minmax(9.5rem,1fr)', format: (_, row) => when(row) },
  { key: 'type', label: t('cash_register.counts.columns.type'), sortable: true, format: (_, row) => t(`cash_register.countTypes.${row.type}`) },
  { key: 'total', label: t('cash_register.counts.columns.total'), sortable: true, align: 'right', format: (_, row) => formatMoney(row.total, locale.value, currency.value) },
  { key: 'notes', label: t('cash_register.counts.columns.notes'), priority: 'low', format: (_, row) => row.notes || '—' },
]);
</script>

<template>
  <DataTable
    testid="cash-register-session-counts"
    server-side
    :rows="result?.rows ?? []"
    :total="result?.total ?? 0"
    :page="table.page.value"
    :page-size="table.pageSize.value"
    :page-size-chooser="false"
    :sort="table.sort.value"
    :sort-dir="table.dir.value"
    :views="['table', 'cards']"
    :card-title="when"
    card-title-column="counted_at"
    :card-icon="() => 'keypad-outline'"
    :entity-label="{ one: $t('cash_register.counts.entity.one'), many: $t('cash_register.counts.entity.many') }"
    :loading="status === 'loading'"
    :error="tableError"
    :labels="{ loading: $t('cash_register.detail.loading'), retry: $t('cash_register.live.retry') }"
    :columns="columns"
    @page-change="table.goToPage"
    @load-more="table.loadMore"
    @sort-change="table.setSort"
    @retry="refresh()"
  >
    <template #empty>
      <EmptyState
        data-testid="cash-register-session-counts-empty"
        icon="keypad-outline"
        :heading="$t('cash_register.detail.noCounts')"
      />
    </template>
  </DataTable>
</template>
