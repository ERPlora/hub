<script setup lang="ts">
// Employees › Approvals (BASE-G145; the old hub's HUB_SHELL-F93), for who runs the business: the live record of each
// action that needed a manager's PIN or badge (`base.approval.list`), read only — nobody edits or deletes a row. When,
// what in the app's words (the old hub showed the command's technical name), who approved it, who asked, how and
// whether it was used; search by person or action, filter by day, action, how and whether it was used (the old hub
// filtered by dates, action and level), and on a phone a card each. Empty, nobody had to approve anything yet; a record
// that cannot be read says so with «Retry».
import { DataTable, type DataTableColumn, type DataTableFilterOption, formatDateTime, StatusPill } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import type { ApprovalRow } from '../operations';

const { t, locale } = useBaseI18n();
const { data, status, refresh } = useLive('base.approval.list', {});

const rows = computed<ApprovalRow[]>(() => data.value?.approvals ?? []);
const failed = computed(() => status.value === 'error' && data.value === undefined);

/** The actions on the record, in words, each once and in alphabetical order: what the «Action» filter offers. */
const actions = computed<DataTableFilterOption[]>(() =>
  [...new Map(rows.value.map((row) => [row.operation, row.action])).entries()]
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, locale.value)),
);
const ways = computed<DataTableFilterOption[]>(() =>
  (['pin', 'badge'] as const).map((way) => ({ value: way, label: t(`base.approvals.way.${way}`) })),
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
    width: '11rem',
    filter: { type: 'daterange' },
  },
  {
    key: 'action',
    label: t('base.approvals.columns.action'),
    width: 'minmax(12rem,2fr)',
    filter: { type: 'select', key: 'operation', options: actions.value },
  },
  { key: 'approved_by', label: t('base.approvals.columns.approvedBy'), width: 'minmax(8rem,1fr)' },
  { key: 'requested_by', label: t('base.approvals.columns.requestedBy'), width: 'minmax(8rem,1fr)' },
  { key: 'way', label: t('base.approvals.columns.way'), cell: 'way', width: '7rem', filter: { type: 'select', options: ways.value } },
  { key: 'used', label: t('base.approvals.columns.used'), cell: 'used', width: '8rem', filter: { type: 'select', options: uses.value } },
]);
</script>

<template>
  <section class="approvals">
    <p class="approvals-intro">
      {{ t('base.approvals.intro') }}
    </p>
    <DataTable
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
      <template #way="{ row }">
        <span data-testid="approvals-way">{{ t(`base.approvals.way.${(row as ApprovalRow).way}`) }}</span>
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
