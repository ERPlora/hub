<script setup lang="ts">
// «Overrides» (temporary changes; SCHEDULE-F05, F06, F13; WORKBOOK «Pantallas», second table): the
// live `schedule.override.list` in a server-side DataTable — From, To, Reason and Status («Closed» or its
// hours) —, «Search override…», filters by its from and to dates, reason and status, sort by any column,
// 50 a page by start. «+» opens «New override» for whoever can add; a row or «Edit» opens «Edit ·
// {reason}» for whoever can change; «Delete» asks first. A refused action is said above the table.
import { ConfirmDialog, type DataTableAction, type DataTableColumn, DataTable, EmptyState, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDate } from '../lib/format';
import { hoursSummary } from '../lib/intervals';
import type { OverrideListIn, OverrideOut } from '../operations';
import FilterPanel, { type FilterSpec, type FilterValues } from './FilterPanel.vue';
import OverrideFormModal from './OverrideFormModal.vue';
import PageNotices, { blockingError } from './PageNotices.vue';

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('schedule.add'));
const canChange = computed(() => session.can('schedule.change'));
const canDelete = computed(() => session.can('schedule.delete'));

const table = useServerTable({ sort: 'start_date' });
const filters = ref<FilterValues>({});
watch(filters, (now) => table.restart({ narrowed: Object.keys(now).length > 0 }));

/** The filters as the query takes them: the status is a yes/no. */
function filterParams(values: FilterValues): Partial<OverrideListIn> {
  const { is_closed: closed, ...rest } = values;
  return { ...rest, ...(closed ? { is_closed: closed === 'true' } : {}) };
}

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList('schedule.override.list', () => ({ ...filterParams(filters.value), ...table.query.value }) as OverrideListIn, () => table.windows.value);
table.followResult(result);

const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' && !blocked.value ? error.value?.message : undefined));

const filterSpecs = computed<FilterSpec[]>(() => [
  { kind: 'range', key: 'start', label: t('schedule.overrides.columns.from'), keys: ['start_from', 'start_to'] },
  { kind: 'range', key: 'end', label: t('schedule.overrides.columns.to'), keys: ['end_from', 'end_to'] },
  { kind: 'text', key: 'reason', label: t('schedule.overrides.columns.reason') },
  {
    kind: 'select',
    key: 'is_closed',
    label: t('schedule.overrides.columns.status'),
    options: [
      { value: 'true', label: t('schedule.closed') },
      { value: 'false', label: t('schedule.open') },
    ],
  },
]);

const columns = computed<DataTableColumn<OverrideOut>[]>(() => [
  { key: 'start_date', label: t('schedule.overrides.columns.from'), sortable: true, format: (_, row) => formatDate(row.start_date, locale.value) },
  { key: 'end_date', label: t('schedule.overrides.columns.to'), sortable: true, format: (_, row) => formatDate(row.end_date, locale.value) },
  { key: 'reason', label: t('schedule.overrides.columns.reason'), sortable: true, priority: 'high' },
  {
    key: 'is_closed',
    label: t('schedule.overrides.columns.status'),
    sortable: true,
    width: 'minmax(10rem,2fr)',
    format: (_, row) => hoursSummary(row, t, locale.value),
  },
]);

const actions = computed<DataTableAction<OverrideOut>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('schedule.actions.edit'), icon: 'create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('schedule.actions.delete'), icon: 'trash-outline', color: 'danger' }] : []),
]);

const editing = ref<OverrideOut | null>(null);
const formOpen = ref(false);
const deleting = ref<OverrideOut | null>(null);
const deleteOpen = ref(false);
const pageError = ref('');
const removal = useCommand('schedule.override.delete');

const failed = (failure: unknown): string => (failure instanceof Error ? failure.message : String(failure));

function openForm(row: OverrideOut | null): void {
  if (row ? !canChange.value : !canAdd.value) return;
  pageError.value = '';
  editing.value = row;
  formOpen.value = true;
}

function onAction({ actionId, row }: { actionId: string; row: OverrideOut }): void {
  pageError.value = '';
  if (actionId === 'edit') openForm(row);
  else if (actionId === 'delete' && canDelete.value) {
    deleting.value = row;
    deleteOpen.value = true;
  }
}

async function remove(): Promise<void> {
  const row = deleting.value;
  if (!row) return;
  try {
    await removal.run({ id: row.id });
  } catch (failure) {
    pageError.value = failed(failure);
  } finally {
    deleteOpen.value = false;
  }
}
</script>

<template>
  <section class="schedule-list">
    <h3
      class="schedule-list__heading"
      data-testid="schedule-overrides-heading"
    >
      {{ $t('schedule.overrides.heading') }}
    </h3>
    <PageNotices
      testid="schedule-overrides"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="schedule-overrides-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="schedule-overrides"
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: OverrideOut) => row.reason"
      :card-icon="() => 'calendar-outline'"
      :entity-label="{ one: $t('schedule.overrides.entity.one'), many: $t('schedule.overrides.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('schedule.overrides.search')"
      :labels="{ add: $t('schedule.overrides.add'), loadError: $t('schedule.overrides.loadError'), retry: $t('schedule.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @row-click="openForm"
      @add="openForm(null)"
      @retry="refresh()"
    >
      <template #filters>
        <FilterPanel
          v-model="filters"
          testid="schedule-overrides"
          :filters="filterSpecs"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="schedule-overrides-empty"
          icon="calendar-outline"
          :heading="table.filtered.value ? $t('schedule.noResults') : $t('schedule.overrides.empty')"
          :message="table.filtered.value ? $t('schedule.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <OverrideFormModal
      v-if="canAdd || canChange"
      v-model:open="formOpen"
      :override="editing"
    />
    <ConfirmDialog
      v-if="canDelete"
      v-model:open="deleteOpen"
      testid="schedule-override-delete"
      tone="danger"
      confirm-icon="ion:trash-outline"
      :title="$t('schedule.delete.title')"
      :message="$t('schedule.delete.message', { name: deleting?.reason ?? '' })"
      :confirm-label="$t('schedule.delete.confirm')"
      :pending="removal.pending.value"
      @confirm="remove"
    />
  </section>
</template>

<style scoped>
.schedule-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  min-height: 0;
}
.schedule-list__heading {
  margin: 0.5rem 0 0;
  font-size: 1rem;
}
</style>
