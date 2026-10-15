<script setup lang="ts">
// The lines of a session (CASH_REGISTER-F11; the old detail's «Movements» table) — or, over another query,
// the lines that fell in no session (F17) — in a server-side DataTable, newest first, 50 a page, table or
// cards (titled by their date and time): When, Type, Amount with its sign, Method and Concept. The sale
// lines are Sales' own, read by the server; they re-run by themselves on a sale, a movement or a close.
import { type DataTableColumn, DataTable, EmptyState, formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { conceptOf, methodOf } from '../lib/lines';
import { formatSignedMoney } from '../lib/money';
import type { MovementListIn, MovementRow } from '../operations';

const props = defineProps<{
  /** Which lines: `{ session_id }` of a session, or `{ unassigned: true }`. */
  query: Pick<MovementListIn, 'session_id' | 'unassigned'>;
  /** Prefix of the table's `data-testid` hooks. */
  testid: string;
  /** What an empty list says. */
  emptyMessage: string;
}>();

const t = useT();
const locale = useLocale();

const table = useServerTable('cash_register.movement.list', {
  sort: 'created_at',
  dir: 'desc',
  maxSearch: 100,
  filters: () => props.query,
});
const { data: result, status, error, refresh } = table;

const tableError = computed(() => (status.value === 'error' ? (error.value?.message ?? t('cash_register.detail.loadError')) : undefined));
const when = (row: MovementRow): string => formatDateTime(row.created_at, locale.value);

const columns = computed<DataTableColumn<MovementRow>[]>(() => [
  { key: 'created_at', label: t('cash_register.lines.columns.when'), sortable: true, width: 'minmax(9.5rem,1fr)', format: (_, row) => when(row) },
  { key: 'type', label: t('cash_register.lines.columns.type'), sortable: true, format: (_, row) => t(`cash_register.types.${row.type}`) },
  {
    key: 'amount',
    label: t('cash_register.lines.columns.amount'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatSignedMoney(row.signed_amount, locale.value),
  },
  { key: 'method_type', label: t('cash_register.lines.columns.method'), sortable: true, format: (_, row) => methodOf(row, t) },
  { key: 'description', label: t('cash_register.lines.columns.concept'), priority: 'low', format: (_, row) => conceptOf(row, t) },
]);
</script>

<template>
  <DataTable
    :testid="testid"
    server-side
    row-key="key"
    :rows="result?.rows ?? []"
    :total="result?.total ?? 0"
    :page="table.page.value"
    :page-size="table.pageSize.value"
    :page-size-chooser="false"
    :sort="table.sort.value"
    :sort-dir="table.dir.value"
    :views="['table', 'cards']"
    :card-title="when"
    card-title-column="created_at"
    :card-icon="() => 'swap-vertical-outline'"
    :entity-label="{ one: $t('cash_register.lines.entity.one'), many: $t('cash_register.lines.entity.many') }"
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
        :data-testid="`${testid}-empty`"
        icon="swap-vertical-outline"
        :heading="emptyMessage"
      />
    </template>
  </DataTable>
</template>
