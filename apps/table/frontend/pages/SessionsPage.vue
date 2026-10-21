<script setup lang="ts">
// Tables → Sessions (WORKBOOK «Pantallas · Sesiones»; TABLE-F21 to F24): the checks of the room, live
// (`table.session.list`), «Open», «Closed» and «All» (Toast's segment), newest first, 50 a page. Columns:
// Table («No table (parked)»), Charged and Closed (not in Open), Zone, Server, Guests, Opened, Time — an
// open check's turns amber and red after the room settings' minutes and keeps counting — and Status.
// «Search table…», filters by zone, server and status. Row actions: Details; Close session on an open one
// (asks first; Sales refuses a check with something ordered and the reason shows in the dialog); Seat
// again on a parked one; Delete on a finished one (owner and admin). Hours are the business's.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
} from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import PageNotices, { blockingError } from '../components/PageNotices.vue';
import RestoreModal from '../components/RestoreModal.vue';
import SessionDetailModal from '../components/SessionDetailModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useNow } from '../composables/useNow';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { clockTime, durationMinutes, durationTone, formatMoney } from '../lib/format';
import type { SessionListIn, SessionOut, SessionStatus, SettingsOut } from '../operations';
import { tableTabs } from '../tabs';

type Segment = 'open' | 'closed' | 'all';
const SEGMENTS: readonly Segment[] = ['open', 'closed', 'all'];
const STATUSES: readonly SessionStatus[] = ['open', 'closed', 'transferred', 'merged', 'parked'];
const FACTORY: SettingsOut = {
  prompt_guests_on_seat: true,
  timer_warning_minutes: 60,
  timer_critical_minutes: 90,
  reserved_lead_minutes: 60,
  timezone: 'Europe/Madrid',
};

const session = useSession();
const t = useT();
const locale = useLocale();
const now = useNow();
const canChange = computed(() => session.can('table.change_session'));
const canDelete = computed(() => session.can('table.delete_session'));

const { data: settingsData } = useLive('table.settings.get', {});
const settings = computed(() => settingsData.value ?? FACTORY);
const { data: zoneList } = useLive('table.zone.list', { limit: 100 });
const { data: waiterList } = useLive('table.waiter.list', { limit: 100 });

const segment = ref<Segment>('open');
const table = useServerTable({ sort: '-opened_at' });
const filters = ref<DataTableFilters>({});
const query = computed<Partial<SessionListIn>>(() => {
  const f = filters.value;
  const status = segment.value === 'all' ? (f.status as SessionStatus | undefined) : segment.value;
  return {
    ...(status ? { status } : {}),
    ...(f.zone_id ? { zone_id: f.zone_id } : {}),
    ...(f.waiter_id ? { waiter_id: f.waiter_id } : {}),
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

function onSegment(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? 'open') as Segment;
  if (!SEGMENTS.includes(value) || value === segment.value) return;
  segment.value = value;
  table.restart({ narrowed: Object.keys(filters.value).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList('table.session.list', () => ({ ...query.value, ...table.query.value }), () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const minutesOf = (row: SessionOut) => durationMinutes(row.opened_at, row.closed_at, now.value);
const when = (iso: string | null) => clockTime(iso, now.value, locale.value, settings.value.timezone);

const columns = computed<DataTableColumn<SessionOut>[]>(() => {
  const finished = segment.value !== 'open';
  return [
    {
      key: 'table_number',
      label: t('table.sessions.columns.table'),
      sortable: true,
      priority: 'high',
      format: (_, row) => row.table_number ?? t('table.sessions.noTable'),
    },
    ...(finished
      ? ([
          { key: 'paid_total', label: t('table.sessions.columns.paid'), sortable: true, align: 'right', format: (_, row) => formatMoney(row.paid_total, locale.value) },
          { key: 'closed_at', label: t('table.sessions.columns.closedAt'), sortable: true, width: 'minmax(8.5rem,1fr)', format: (_, row) => when(row.closed_at) },
        ] as DataTableColumn<SessionOut>[])
      : []),
    {
      key: 'zone_name',
      label: t('table.sessions.columns.zone'),
      sortable: true,
      format: (_, row) => row.zone_name ?? t('table.none'),
      filter: { type: 'select', key: 'zone_id', options: (zoneList.value?.rows ?? []).map((zone) => ({ value: zone.id, label: zone.name })) },
    },
    {
      key: 'waiter_name',
      label: t('table.sessions.columns.waiter'),
      format: (_, row) => row.waiter_name || t('table.none'),
      filter: { type: 'select', key: 'waiter_id', options: (waiterList.value?.rows ?? []).map((waiter) => ({ value: waiter.id, label: waiter.name })) },
    },
    { key: 'guests_count', label: t('table.sessions.columns.guests'), sortable: true, align: 'right', format: (_, row) => t('table.pax', { count: row.guests_count }) },
    { key: 'opened_at', label: t('table.sessions.columns.openedAt'), sortable: true, width: 'minmax(8.5rem,1fr)', format: (_, row) => when(row.opened_at) },
    {
      key: 'duration',
      label: t('table.sessions.columns.duration'),
      align: 'right',
      cell: 'duration',
      format: (_, row) => t('table.minutes', { minutes: minutesOf(row) }),
    },
    {
      key: 'status',
      label: t('table.sessions.columns.status'),
      sortable: true,
      format: (_, row) => t(`table.sessionStatus.${row.status}`),
      ...(segment.value === 'all'
        ? { filter: { type: 'select' as const, options: STATUSES.map((value) => ({ value, label: t(`table.sessionStatus.${value}`) })) } }
        : {}),
    },
  ];
});

const actions = computed<DataTableAction<SessionOut>[]>(() => [
  { id: 'detail', label: t('table.sessions.actions.detail'), icon: 'information-circle-outline' },
  ...(canChange.value
    ? [
        { id: 'close', label: t('table.sessions.actions.close'), icon: 'checkmark-circle-outline', color: 'danger', hidden: (row: SessionOut) => row.status !== 'open' },
        { id: 'restore', label: t('table.sessions.actions.restore'), icon: 'arrow-undo-outline', hidden: (row: SessionOut) => row.status !== 'parked' },
      ]
    : []),
  ...(canDelete.value
    ? [
        {
          id: 'delete',
          label: t('table.sessions.actions.delete'),
          icon: 'trash-outline',
          color: 'danger',
          menuOnly: true,
          hidden: (row: SessionOut) => row.status === 'open' || row.status === 'parked',
        },
      ]
    : []),
]);

const target = ref<SessionOut | null>(null);
const detailOpen = ref(false);
const restoreOpen = ref(false);
const closeOpen = ref(false);
const deleteOpen = ref(false);
const close = useCommand('table.session.close');
const removal = useCommand('table.session.delete');

function onAction({ actionId, row }: { actionId: string; row: SessionOut }): void {
  target.value = row;
  if (actionId === 'detail') detailOpen.value = true;
  if (actionId === 'restore') restoreOpen.value = true;
  if (actionId === 'close') {
    close.error.value = null;
    closeOpen.value = true;
  }
  if (actionId === 'delete') {
    removal.error.value = null;
    deleteOpen.value = true;
  }
}

async function confirmClose(): Promise<void> {
  if (!target.value) return;
  try {
    await close.run({ id: target.value.id, order_id: target.value.order_id });
  } catch {
    return; // The dialog says why.
  }
  closeOpen.value = false;
}

async function confirmDelete(): Promise<void> {
  if (!target.value) return;
  try {
    await removal.run({ id: target.value.id });
  } catch {
    return;
  }
  deleteOpen.value = false;
}
</script>

<template>
  <AppPage
    :title="$t('table.title')"
    content-layout="fill"
    :tabs="tableTabs($t, { settings: session.can('table.manage_settings') })"
    :tabs-label="$t('table.tabs.label')"
  >
    <PageNotices
      testid="table-sessions"
      :status="status"
      :error="error"
    />
    <ion-segment
      class="table-sessions__segment"
      data-testid="table-sessions-segment"
      :value="segment"
      :aria-label="$t('table.sessions.segment.label')"
      @ion-change="onSegment"
    >
      <ion-segment-button
        v-for="value in SEGMENTS"
        :key="value"
        :value="value"
        :data-testid="`table-sessions-segment-${value}`"
      >
        <ion-label>{{ $t(`table.sessions.segment.${value}`) }}</ion-label>
      </ion-segment-button>
    </ion-segment>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="table-sessions"
      fill
      server-side
      searchable
      filterable
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: SessionOut) => (row.table_number ? t('table.tableLabel', { number: row.table_number }) : t('table.sessions.noTable'))"
      :card-icon="() => 'time-outline'"
      :entity-label="{ one: $t('table.sessions.entity.one'), many: $t('table.sessions.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('table.sessions.loadError') : undefined"
      :actions="actions"
      :search-placeholder="$t('table.sessions.search')"
      :labels="{ loadError: $t('table.sessions.loadError'), retry: $t('table.live.retry') }"
      :columns="columns"
      :card-breakpoint="900"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @retry="refresh()"
    >
      <template #duration="{ row }">
        <span
          :class="`table-sessions__time table-sessions__time--${durationTone(row.status, minutesOf(row), settings)}`"
          :data-tone="durationTone(row.status, minutesOf(row), settings)"
        >{{ $t('table.minutes', { minutes: minutesOf(row) }) }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="table-sessions-empty"
          icon="time-outline"
          :heading="table.filtered.value ? $t('table.noResults') : $t('table.sessions.empty')"
          :message="table.filtered.value ? $t('table.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <SessionDetailModal
      v-model:open="detailOpen"
      :session="target"
      :settings="settings"
      :now="now"
    />
    <RestoreModal
      v-if="restoreOpen"
      v-model:open="restoreOpen"
      :session="target"
    />
    <ConfirmDialog
      v-model:open="closeOpen"
      testid="table-sessions-close"
      tone="danger"
      :title="t('table.sessions.close.title')"
      :message="target ? t('table.sessions.close.impact', { number: target.table_number ?? '—', count: target.guests_count }) : ''"
      :confirm-label="t('table.sessions.close.confirm')"
      :cancel-label="t('table.cancel')"
      :pending="close.pending.value"
      :error="close.error.value"
      @confirm="confirmClose"
      @cancel="closeOpen = false"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="table-sessions-delete"
      tone="danger"
      :title="t('table.sessions.delete.title')"
      :message="t('table.sessions.delete.message')"
      :confirm-label="t('table.sessions.delete.confirm')"
      :cancel-label="t('table.cancel')"
      :pending="removal.pending.value"
      :error="removal.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>

<style scoped>
.table-sessions__segment {
  max-width: 28rem;
  margin-bottom: 0.6rem;
}
.table-sessions__segment ion-segment-button {
  min-height: 44px;
}
.table-sessions__time--warning {
  color: var(--ion-color-warning-shade, #b06c00);
  font-weight: 600;
}
.table-sessions__time--critical {
  color: var(--ion-color-danger, #d9480f);
  font-weight: 700;
}
</style>
