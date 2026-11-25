<script setup lang="ts">
// Employees › Approvals: the read-only record of each action a manager may approve, with their PIN or badge or done by
// whoever needs no approval. Each action is named in its app's words, never by the command's technical name.
import {
  DataTable,
  type DataTableColumn,
  type DataTableFilterOption,
  type DataTableFilters,
  formatDateTime,
  StatusPill,
} from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed, ref } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { ApprovalExportQuery, ApprovalRow, ApprovalWay } from '../operations/approvals';
import ApprovalsExportButton from './ApprovalsExportButton.vue';

const { t, locale } = useBaseI18n();
const { data, status, refresh } = useLive('base.approval.list', {});

const rows = computed<ApprovalRow[]>(() => data.value?.approvals ?? []);
const failed = computed(() => status.value === 'error' && data.value === undefined);

// What the person has on screen, for «Export CSV»: the search and the active filters (the table drops the empty ones).
const search = ref('');
const filters = ref<DataTableFilters>({});
const exportQuery = computed<ApprovalExportQuery>(() => {
  const words = search.value.trim();
  return { ...(words ? { search: words } : {}), ...filters.value };
});

/** The actions on the record, by their names without figures (a row says «… 50 %»), each once and in alphabetical
 *  order: what the «Action» filter offers. */
const actions = computed<DataTableFilterOption[]>(() =>
  [...new Map(rows.value.map((row) => [row.operation, row.operation_label])).entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, locale.value)),
);
const ways = computed<DataTableFilterOption[]>(() =>
  (['pin', 'badge', 'role'] satisfies ApprovalWay[]).map((way) => ({ value: way, label: t(`base.approvals.way.${way}`) })),
);
const uses = computed<DataTableFilterOption[]>(() => [
  { value: 'true', label: t('base.approvals.used') },
  { value: 'false', label: t('base.approvals.unused') },
]);

const columns = computed<DataTableColumn<ApprovalRow>[]>(() => [
  {
    key: 'at',
    label: t('base.approvals.columns.at'),
    format: (value: unknown) => formatDateTime(value as string, locale.value),
    filter: { type: 'daterange' },
  },
  {
    key: 'action',
    label: t('base.approvals.columns.action'),
    filter: { type: 'select', key: 'operation', options: actions.value },
  },
  { key: 'approved_by', label: t('base.approvals.columns.approvedBy') },
  { key: 'requested_by', label: t('base.approvals.columns.requestedBy') },
  {
    key: 'way',
    label: t('base.approvals.columns.way'),
    format: (value: unknown) => t(`base.approvals.way.${value as ApprovalWay}`),
    filter: { type: 'select', options: ways.value },
  },
  { key: 'used', label: t('base.approvals.columns.used'), cell: 'used', filter: { type: 'select', options: uses.value } },
]);
</script>

<template>
  <section class="approvals">
    <p class="approvals-intro">
      {{ t('base.approvals.intro') }}
    </p>
    <DataTable
      v-model:search="search"
      v-model:filters="filters"
      testid="approvals"
      :columns="columns"
      :rows="rows"
      :page-size="20"
      :page-size-options="[]"
      :views="['table', 'cards']"
      filterable
      :card-title="(row: ApprovalRow) => row.action"
      card-title-column="action"
      :search-keys="['action', 'approved_by', 'requested_by']"
      :search-placeholder="t('base.approvals.search')"
      :empty-message="t('base.approvals.empty')"
      :loading="data === undefined && !failed"
      :error="failed ? t('base.approvals.error') : undefined"
      @retry="refresh()"
    >
      <template #toolbar>
        <ApprovalsExportButton :query="exportQuery" />
      </template>
      <template #used="{ row }">
        <StatusPill
          data-testid="approvals-used"
          size="sm"
          :tone="(row as ApprovalRow).used ? 'success' : 'neutral'"
          :label="t((row as ApprovalRow).used ? 'base.approvals.used' : 'base.approvals.unused')"
        />
      </template>
    </DataTable>
  </section>
</template>

<style scoped>
.approvals {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.approvals-intro {
  margin: 0;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
}
</style>
