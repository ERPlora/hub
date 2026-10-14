<script setup lang="ts">
// Staff → Time Off (WORKBOOK «Pantallas · Ausencias»; STAFF-F08, F17–F20, F24): the live
// `staff.time_off.list` — Member, Type, From, To (a part day with its hours) and Status, never the
// reason —, «Search member…», sort by any column (newest first), filters, 50 a page. Row actions where
// they apply: «Approve» and «Reject» a pending request and «Cancel» (confirmed) a pending or approved
// one for whoever manages time off; an employee cancels only their own pending request. «+» registers
// anyone's (managers) or asks for one's own. «My time off» (`staff.time_off.mine`, with the reason) for
// whoever has a linked record. Every change comes back through the stream: nothing here refetches.
import { ConfirmDialog, type DataTableAction, type DataTableColumn, DataTable, EmptyState, InlineFeedback, StatusPill } from '@erplora/ui/components';
import { useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import FilterPanel, { type FilterSpec, type FilterValues } from '../components/FilterPanel.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import TimeOffFormModal from '../components/TimeOffFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { LEAVE_TYPES, REQUEST_STATUSES, requestStatusTone } from '../lib/enums';
import { formatDate, formatTime } from '../lib/format';
import { memberSearch } from '../lib/pickers';
import type { TimeOffDetailOut, TimeOffListIn, TimeOffOut } from '../operations';
import { staffTabs } from '../tabs';

type View = 'all' | 'mine';

const session = useSession();
const t = useT();
const locale = useLocale();
const client = useLiveClient();

const canManage = computed(() => session.can('staff.manage_time_off'));
const canRequest = computed(() => session.can('staff.request_time_off'));
const canSettings = computed(() => session.can('staff.manage_settings'));

// ── The lists ──────────────────────────────────────────────────────────────────────────────────
const view = ref<View>('all');
const table = useServerTable({ sort: '-start_date' });
const filters = ref<FilterValues>({});
watch([filters, view], ([now, which]) => table.restart({ narrowed: which === 'all' && Object.keys(now).length > 0 }));

/** The filters as the query takes them: Full day is a yes/no. */
function filterParams(values: FilterValues): Partial<TimeOffListIn> {
  const { is_full_day: fullDay, ...rest } = values;
  return { ...rest, ...(fullDay ? { is_full_day: fullDay === 'true' } : {}) } as Partial<TimeOffListIn>;
}

const all = useLiveList(
  'staff.time_off.list',
  () => ({ ...filterParams(filters.value), ...table.query.value }),
  () => table.windows.value,
);
/** One's own requests, with their reason (STAFF-F08). */
const mineList = useLiveList('staff.time_off.mine', () => ({}), () => table.windows.value);
/** One's own record: who «mine» is, and whether there is a «My time off» at all. */
const { data: mine } = useLive('staff.member.mine', {});

const current = computed(() => (view.value === 'mine' ? mineList : all));
const result = computed(() => current.value.data.value as { rows: TimeOffOut[]; total: number; offset: number } | undefined);
const status = computed(() => current.value.status.value);
const error = computed(() => current.value.error.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));
const ownId = computed(() => mine.value?.member?.id ?? null);

/** Switching view starts afresh: «My time off» has no search, and its own order (no sort). */
function setView(event: CustomEvent<{ value?: unknown }>): void {
  const next: View = event.detail.value === 'mine' ? 'mine' : 'all';
  if (next === view.value) return;
  table.search.value = '';
  view.value = next;
}

/** Only «All» sorts on the server (`staff.time_off.mine` gives one's own in its own order). */
const sortable = computed(() => view.value === 'all');

const filterSpecs = computed<FilterSpec[]>(() => [
  { kind: 'search', key: 'member_id', label: t('staff.timeOff.filters.member'), load: memberSearch(client) },
  { kind: 'select', key: 'leave_type', label: t('staff.timeOff.columns.type'), options: LEAVE_TYPES.map((value) => ({ value, label: t(`staff.leaveType.${value}`) })) },
  {
    kind: 'select',
    key: 'status',
    label: t('staff.timeOff.columns.status'),
    options: REQUEST_STATUSES.map((value) => ({ value, label: t(`staff.requestStatus.${value}`) })),
  },
  {
    kind: 'select',
    key: 'is_full_day',
    label: t('staff.timeOff.filters.fullDay'),
    options: [
      { value: 'true', label: t('staff.yes') },
      { value: 'false', label: t('staff.no') },
    ],
  },
  { kind: 'range', key: 'dates', label: t('staff.timeOff.filters.dates'), keys: ['date_from', 'date_to'], type: 'date' },
]);

/** A day, with the hour of a part-day absence («10/11/2026 09:00»). */
function when(date: string, time: string | null, row: TimeOffOut): string {
  const day = formatDate(date, locale.value);
  return row.is_full_day || !time ? day : `${day} ${formatTime(time)}`;
}

const columns = computed<DataTableColumn<TimeOffOut>[]>(() => [
  { key: 'member_name', label: t('staff.timeOff.columns.member'), sortable: sortable.value, priority: 'high' },
  { key: 'leave_type', label: t('staff.timeOff.columns.type'), sortable: sortable.value, format: (_, row) => t(`staff.leaveType.${row.leave_type}`) },
  { key: 'start_date', label: t('staff.timeOff.columns.from'), sortable: sortable.value, format: (_, row) => when(row.start_date, row.start_time, row) },
  { key: 'end_date', label: t('staff.timeOff.columns.to'), sortable: sortable.value, format: (_, row) => when(row.end_date, row.end_time, row) },
  {
    key: 'status',
    label: t('staff.timeOff.columns.status'),
    sortable: sortable.value,
    cell: 'status',
    format: (_, row) => t(`staff.requestStatus.${row.status}`),
  },
  ...(view.value === 'mine'
    ? [
        {
          key: 'reason',
          label: t('staff.timeOff.columns.reason'),
          priority: 'low' as const,
          format: (_: unknown, row: TimeOffOut) => (row as TimeOffDetailOut).reason?.trim() || '—',
        },
      ]
    : []),
]);

// ── Row actions ────────────────────────────────────────────────────────────────────────────────
const pageError = ref('');
const busy = ref<string | null>(null);

/** Cancel: a manager any pending or approved request; anyone else only their own pending one. */
function cancellable(row: TimeOffOut): boolean {
  if (canManage.value) return row.status === 'pending' || row.status === 'approved';
  return canRequest.value && row.status === 'pending' && ownId.value !== null && row.member_id === ownId.value;
}

const actions = computed<DataTableAction<TimeOffOut>[]>(() => [
  ...(canManage.value
    ? [
        {
          id: 'approve',
          label: t('staff.timeOff.actions.approve'),
          icon: 'checkmark-circle-outline',
          color: 'primary',
          hidden: (row: TimeOffOut) => row.status !== 'pending',
          loading: (row: TimeOffOut) => busy.value === row.id,
        },
        {
          id: 'reject',
          label: t('staff.timeOff.actions.reject'),
          icon: 'close-circle-outline',
          hidden: (row: TimeOffOut) => row.status !== 'pending',
          loading: (row: TimeOffOut) => busy.value === row.id,
        },
      ]
    : []),
  ...(canManage.value || canRequest.value
    ? [{ id: 'cancel', label: t('staff.timeOff.actions.cancel'), icon: 'ban-outline', color: 'danger', hidden: (row: TimeOffOut) => !cancellable(row) }]
    : []),
]);

const approval = useCommand('staff.time_off.approve');
const rejection = useCommand('staff.time_off.reject');
const cancellation = useCommand('staff.time_off.cancel');
const cancelling = ref<TimeOffOut | null>(null);
const cancelOpen = ref(false);

const failed = (failure: unknown): string => (failure instanceof Error ? failure.message : String(failure));

async function decide(row: TimeOffOut, command: typeof approval | typeof rejection): Promise<void> {
  busy.value = row.id;
  try {
    await command.run({ id: row.id });
  } catch (failure) {
    pageError.value = failed(failure);
  } finally {
    busy.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: TimeOffOut }): void {
  pageError.value = '';
  if (actionId === 'approve' && canManage.value && row.status === 'pending') void decide(row, approval);
  else if (actionId === 'reject' && canManage.value && row.status === 'pending') void decide(row, rejection);
  else if (actionId === 'cancel' && cancellable(row)) {
    cancelling.value = row;
    cancelOpen.value = true;
  }
}

async function cancel(): Promise<void> {
  const row = cancelling.value;
  if (!row) return;
  try {
    await cancellation.run({ id: row.id });
  } catch (failure) {
    pageError.value = failed(failure);
  } finally {
    cancelOpen.value = false;
  }
}

const cancelMessage = computed(() =>
  cancelling.value
    ? t('staff.timeOff.cancel.message', {
        name: cancelling.value.member_name,
        from: formatDate(cancelling.value.start_date, locale.value),
        to: formatDate(cancelling.value.end_date, locale.value),
      })
    : '',
);

// ── «+» ────────────────────────────────────────────────────────────────────────────────────────
const formOpen = ref(false);
function add(): void {
  pageError.value = '';
  formOpen.value = true;
}
</script>

<template>
  <AppPage
    :title="$t('staff.title')"
    :tabs="staffTabs($t, { settings: canSettings })"
    :tabs-label="$t('staff.tabs.label')"
  >
    <PageNotices
      testid="staff-time-off"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="staff-time-off-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="staff-time-off"
      server-side
      :searchable="view === 'all'"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="sortable ? table.sort.value : undefined"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: TimeOffOut) => row.member_name"
      :card-icon="() => 'calendar-outline'"
      :entity-label="{ one: $t('staff.timeOff.entity.one'), many: $t('staff.timeOff.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? error?.message : undefined"
      :addable="canManage || canRequest"
      :actions="actions"
      :search-placeholder="$t('staff.timeOff.search')"
      :labels="{ add: $t('staff.add'), loadError: $t('staff.timeOff.loadError'), retry: $t('staff.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @add="add"
      @retry="current.refresh()"
    >
      <template #filters>
        <ion-select
          v-if="mine?.member"
          data-testid="staff-time-off-whose"
          interface="popover"
          :aria-label="$t('staff.timeOff.view.label')"
          :value="view"
          @ion-change="setView"
        >
          <ion-select-option value="all">
            {{ $t('staff.timeOff.view.all') }}
          </ion-select-option>
          <ion-select-option value="mine">
            {{ $t('staff.timeOff.view.mine') }}
          </ion-select-option>
        </ion-select>
        <FilterPanel
          v-if="view === 'all'"
          v-model="filters"
          testid="staff-time-off"
          :filters="filterSpecs"
        />
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="requestStatusTone(row.status)"
          :label="$t(`staff.requestStatus.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="staff-time-off-empty"
          icon="calendar-outline"
          :heading="table.filtered.value && view === 'all' ? $t('staff.noResults') : $t('staff.timeOff.empty')"
          :message="table.filtered.value && view === 'all' ? $t('staff.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <TimeOffFormModal
      v-if="canManage || canRequest"
      v-model:open="formOpen"
      :mode="canManage ? 'create' : 'request'"
    />
    <ConfirmDialog
      v-model:open="cancelOpen"
      testid="staff-time-off-cancel"
      tone="danger"
      confirm-icon="ion:ban-outline"
      :title="$t('staff.timeOff.cancel.title')"
      :message="cancelMessage"
      :confirm-label="$t('staff.timeOff.cancel.confirm')"
      :cancel-label="$t('staff.timeOff.cancel.keep')"
      :pending="cancellation.pending.value"
      @confirm="cancel"
    />
  </AppPage>
</template>
