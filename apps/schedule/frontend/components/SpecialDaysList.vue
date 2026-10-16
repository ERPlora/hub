<script setup lang="ts">
// «Special days» (SCHEDULE-F04, F06, F13; WORKBOOK «Pantallas · Días especiales»): the live
// `schedule.special_day.list` in a server-side DataTable — Date, Name, Status («Closed» or its hours,
// interval by interval) and Yearly —, «Search special day…», filters behind the table's funnel by date
// (from–to), name, status and yearly, sort by any column, 50 a page by date. «+» opens «New special day» for whoever can add; a row
// or «Edit» opens «Edit · {name}» for whoever can change; «Delete» asks first. A refused action is said
// above the table; a new or changed row arrives through the stream.
import {
  ConfirmDialog,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  type DataTableLabels,
  DataTable,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatDate } from '../lib/format';
import { hoursSummary } from '../lib/intervals';
import type { SpecialDayListIn, SpecialDayOut } from '../operations';
import PageNotices, { blockingError } from './PageNotices.vue';
import SpecialDayFormModal from './SpecialDayFormModal.vue';

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('schedule.add'));
const canChange = computed(() => session.can('schedule.change'));
const canDelete = computed(() => session.can('schedule.delete'));

const table = useServerTable({ sort: 'date' });
/** The table's filters (its funnel): a filter not in use is absent. */
const filters = ref<DataTableFilters>({});
watch(filters, (now) => table.restart({ narrowed: Object.keys(now).length > 0 }));

/** The filters as the query takes them: status and yearly are yes/no. */
function filterParams(values: DataTableFilters): Partial<SpecialDayListIn> {
  const { is_closed: closed, recurring_yearly: yearly, ...rest } = values;
  return {
    ...rest,
    ...(closed ? { is_closed: closed === 'true' } : {}),
    ...(yearly ? { recurring_yearly: yearly === 'true' } : {}),
  };
}

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList('schedule.special_day.list', () => ({ ...filterParams(filters.value), ...table.query.value }) as SpecialDayListIn, () => table.windows.value);
table.followResult(result);

const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' && !blocked.value ? error.value?.message : undefined));

const columns = computed<DataTableColumn<SpecialDayOut>[]>(() => [
  {
    key: 'date',
    label: t('schedule.specialDays.columns.date'),
    sortable: true,
    format: (_, row) => formatDate(row.date, locale.value),
    filter: { type: 'daterange', keys: ['date_from', 'date_to'] },
  },
  { key: 'name', label: t('schedule.specialDays.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  {
    key: 'is_closed',
    label: t('schedule.specialDays.columns.status'),
    sortable: true,
    width: 'minmax(10rem,2fr)',
    format: (_, row) => hoursSummary(row, t, locale.value),
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('schedule.closed') },
        { value: 'false', label: t('schedule.open') },
      ],
    },
  },
  {
    key: 'recurring_yearly',
    label: t('schedule.specialDays.columns.yearly'),
    sortable: true,
    format: (_, row) => (row.recurring_yearly ? t('schedule.yes') : t('schedule.no')),
    filter: { type: 'boolean' },
  },
]);

/** The screen has two lists (schedules#58): its funnel and view buttons say they are the special
 *  days'. DataTable fills the `{n}` of the count itself. */
const tableLabels = computed<Partial<DataTableLabels>>(() => ({
  add: t('schedule.specialDays.add'),
  loadError: t('schedule.specialDays.loadError'),
  retry: t('schedule.live.retry'),
  filters: t('schedule.specialDays.table.filters'),
  filtersActiveOne: t('schedule.specialDays.table.filtersActiveOne', { n: '{n}' }),
  filtersActiveMany: t('schedule.specialDays.table.filtersActiveMany', { n: '{n}' }),
  viewList: t('schedule.specialDays.table.viewList'),
  viewCards: t('schedule.specialDays.table.viewCards'),
}));

const actions = computed<DataTableAction<SpecialDayOut>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('schedule.actions.edit'), icon: 'create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('schedule.actions.delete'), icon: 'trash-outline', color: 'danger' }] : []),
]);

const editing = ref<SpecialDayOut | null>(null);
const formOpen = ref(false);
const deleting = ref<SpecialDayOut | null>(null);
const deleteOpen = ref(false);
const pageError = ref('');
const removal = useCommand('schedule.special_day.delete');

const failed = (failure: unknown): string => (failure instanceof Error ? failure.message : String(failure));

function openForm(row: SpecialDayOut | null): void {
  if (row ? !canChange.value : !canAdd.value) return;
  pageError.value = '';
  editing.value = row;
  formOpen.value = true;
}

function onAction({ actionId, row }: { actionId: string; row: SpecialDayOut }): void {
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
      data-testid="schedule-special-days-heading"
    >
      {{ $t('schedule.specialDays.heading') }}
    </h3>
    <PageNotices
      testid="schedule-special-days"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="schedule-special-days-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="schedule-special-days"
      server-side
      searchable
      filterable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: SpecialDayOut) => row.name"
      :card-icon="() => 'calendar-outline'"
      :entity-label="{ one: $t('schedule.specialDays.entity.one'), many: $t('schedule.specialDays.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('schedule.specialDays.search')"
      :labels="tableLabels"
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
      <template #empty>
        <EmptyState
          data-testid="schedule-special-days-empty"
          icon="calendar-outline"
          :heading="table.filtered.value ? $t('schedule.noResults') : $t('schedule.specialDays.empty')"
          :message="table.filtered.value ? $t('schedule.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <SpecialDayFormModal
      v-if="canAdd || canChange"
      v-model:open="formOpen"
      :special-day="editing"
    />
    <ConfirmDialog
      v-if="canDelete"
      v-model:open="deleteOpen"
      testid="schedule-special-day-delete"
      tone="danger"
      confirm-icon="ion:trash-outline"
      :title="$t('schedule.delete.title')"
      :message="$t('schedule.delete.message', { name: deleting?.name ?? '' })"
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
