<script setup lang="ts">
// Reservations → Reservations (WORKBOOK «Pantallas · Reservas»; RESERVATION-F05 to F12, F20, F23): the book
// of a day on the business's clock (its zone comes with the settings). The day bar (DayBar) gives the day
// and its figures (`reservation.availability.day`, live); the list follows the live
// `reservation.reservation.list` of that day by time — or, searching a guest's name, phone or email, the
// whole book in calendar order (the old module's rule). Columns Date, Time, Guest, Phone, Party, Table and
// Status, filters by time, guest, phone, party and status, list or cards, 50 a page. «New reservation» and a
// row open the booking panel; per row Confirm, Seat (it seats the table and opens its check), Complete,
// Cancel and No-show (asking first), Edit and Delete (the owner and the admin), as its status allows.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';

import DayBar from '../components/DayBar.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import ReservationFormModal from '../components/ReservationFormModal.vue';
import StepDialog, { type StepKind } from '../components/StepDialog.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatShortDate, formatTime, todayIn, wallNowIn } from '../lib/clock';
import { allows, type RowAction, statusTone } from '../lib/states';
import type { ReservationOut, ReservationStatus } from '../operations';
import { reservationTabs } from '../tabs';

/** The zone until the settings say the business's (phase 1: Europe/Madrid, as the server). */
const FALLBACK_ZONE = 'Europe/Madrid';
const STATUSES: readonly ReservationStatus[] = ['pending', 'confirmed', 'seated', 'completed', 'cancelled', 'no_show'];

const session = useSession();
const t = useT();
const locale = useLocale();
const canAdd = computed(() => session.can('reservation.add_reservation'));
const canChange = computed(() => session.can('reservation.change_reservation'));
const canDelete = computed(() => session.can('reservation.delete_reservation'));

const { data: settings } = useLive('reservation.settings.get', {});
const zone = computed(() => settings.value?.timezone ?? FALLBACK_ZONE);
const clock = shallowRef(new Date());
let ticker: ReturnType<typeof setInterval> | null = null;
onMounted(() => {
  ticker = setInterval(() => (clock.value = new Date()), 60_000);
});
onBeforeUnmount(() => {
  if (ticker) clearInterval(ticker);
});
const today = computed(() => todayIn(zone.value, clock.value));
const now = computed(() => wallNowIn(zone.value, clock.value).slice(11, 16));

const day = ref(todayIn(FALLBACK_ZONE, clock.value));
const dayTouched = ref(false);
watch(today, (value) => {
  if (!dayTouched.value) day.value = value;
});
function setDay(value: string): void {
  dayTouched.value = true;
  day.value = value;
  table.goToPage(0);
}

const figures = useLive('reservation.availability.day', () => ({ date: day.value }));
const figuresFailed = computed(() => (figures.status.value === 'error' ? (figures.error.value?.message ?? 'error') : null));

const table = useServerTable({ sort: 'starts_at' });
const filters = ref<DataTableFilters>({});
const searching = computed(() => table.search.value.trim() !== '');
const whole = (value: string | undefined) => (value && /^\d+$/.test(value) ? Number(value) : undefined);
const query = computed(() => {
  const f = filters.value;
  const from = whole(f.party_size_from);
  const to = whole(f.party_size_to);
  return {
    // A search looks through the whole book: the guest who booked next Friday is found from today.
    ...(searching.value ? {} : { date_from: day.value, date_to: day.value }),
    ...(f.status ? { status: f.status as ReservationStatus } : {}),
    ...(f.guest_name ? { guest_name: f.guest_name } : {}),
    ...(f.guest_phone ? { guest_phone: f.guest_phone } : {}),
    ...(f.time ? { time: f.time } : {}),
    ...(from ? { party_size_from: from } : {}),
    ...(to ? { party_size_to: to } : {}),
  };
});

function onFilters(next: DataTableFilters): void {
  filters.value = next;
  table.restart({ narrowed: Object.keys(next).length > 0 });
}

function clearQuery(): void {
  table.search.value = '';
  filters.value = {};
  table.restart({ narrowed: false });
}

const { data: result, status, error, refresh } = useLiveList(
  'reservation.reservation.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const guestOf = (row: ReservationOut): string => row.guest_name || t('reservation.erasedCustomer');

const columns = computed<DataTableColumn<ReservationOut>[]>(() => [
  { key: 'date', label: t('reservation.list.columns.date'), format: (_, row) => formatShortDate(row.date, locale.value) },
  {
    key: 'time',
    label: t('reservation.list.columns.time'),
    sortable: true,
    format: (_, row) => formatTime(row.time, locale.value),
    filter: { type: 'text' },
  },
  { key: 'guest_name', label: t('reservation.list.columns.guest'), sortable: true, priority: 'high', cell: 'guest', filter: { type: 'text' } },
  { key: 'guest_phone', label: t('reservation.list.columns.phone'), sortable: true, priority: 'low', filter: { type: 'text' } },
  {
    key: 'party_size',
    label: t('reservation.list.columns.party'),
    sortable: true,
    align: 'right',
    format: (_, row) => String(row.party_size),
    filter: { type: 'range' },
  },
  { key: 'table', label: t('reservation.list.columns.table'), sortable: true, format: (_, row) => row.table_label || '—' },
  {
    key: 'status',
    label: t('reservation.list.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`reservation.status.${value}`) })) },
  },
  { key: 'source', label: t('reservation.list.columns.source'), hidden: true, format: (_, row) => t(`reservation.source.${row.source}`) },
]);

const ACTIONS: ReadonlyArray<{ id: RowAction; key: string; icon: string; color?: string; showLabel?: boolean }> = [
  { id: 'confirm', key: 'confirm', icon: 'checkmark-outline', color: 'primary', showLabel: true },
  { id: 'seat', key: 'seat', icon: 'people-outline', color: 'success', showLabel: true },
  { id: 'complete', key: 'complete', icon: 'checkmark-circle-outline', color: 'medium', showLabel: true },
  { id: 'cancel', key: 'cancel', icon: 'close-outline', color: 'danger' },
  { id: 'no_show', key: 'noShow', icon: 'ban-outline', color: 'danger' },
  { id: 'edit', key: 'edit', icon: 'create-outline' },
  { id: 'delete', key: 'delete', icon: 'trash-outline', color: 'danger' },
];

const actions = computed<DataTableAction<ReservationOut>[]>(() =>
  ACTIONS.filter((action) => (action.id === 'delete' ? canDelete.value : canChange.value)).map((action) => ({
    id: action.id,
    label: t(`reservation.actions.${action.key}`),
    icon: action.icon,
    color: action.color,
    showLabel: action.showLabel,
    hidden: (row: ReservationOut) => !allows(action.id, row.status),
  })),
);

// The booking panel and the steps that ask first
const formOpen = ref(false);
const editing = shallowRef<ReservationOut | null>(null);
const stepOpen = ref(false);
const stepKind = ref<StepKind>('cancel');
const stepRow = shallowRef<ReservationOut | null>(null);
const pageError = ref<string | null>(null);
const outcome = ref<string | null>(null);

function openForm(row: ReservationOut | null): void {
  editing.value = row;
  formOpen.value = true;
}

const confirmCommand = useCommand('reservation.reservation.confirm');
const seatCommand = useCommand('reservation.reservation.seat');
const completeCommand = useCommand('reservation.reservation.complete');

async function quickStep(action: 'confirm' | 'seat' | 'complete', row: ReservationOut): Promise<void> {
  pageError.value = null;
  outcome.value = null;
  const command = { confirm: confirmCommand, seat: seatCommand, complete: completeCommand }[action];
  try {
    const done = await command.run({ id: row.id });
    if (action === 'seat') {
      outcome.value = done.table_session_id
        ? t('reservation.outcome.seated', { guest: guestOf(done), table: done.table_label })
        : t('reservation.outcome.seatedNoTable', { guest: guestOf(done) });
    }
  } catch (caught) {
    pageError.value = (caught as Error)?.message || t('reservation.actions.failed');
  }
}

function onAction({ actionId, row }: { actionId: string; row: ReservationOut }): void {
  if (actionId === 'edit') return openForm(row);
  if (actionId === 'confirm' || actionId === 'seat' || actionId === 'complete') {
    void quickStep(actionId, row);
    return;
  }
  if (actionId === 'cancel' || actionId === 'no_show' || actionId === 'delete') {
    stepKind.value = actionId;
    stepRow.value = row;
    stepOpen.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="$t('reservation.title')"
    content-layout="fill"
    :tabs="reservationTabs($t, { settings: session.can('reservation.manage_settings') })"
    :tabs-label="$t('reservation.tabs.label')"
  >
    <DayBar
      :day="day"
      :today="today"
      :now="now"
      :figures="figures.data.value"
      :failed="figuresFailed"
      @update:day="setDay"
    />
    <PageNotices
      testid="reservation-list"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      dismissible
      data-testid="reservation-list-page-error"
      :heading="$t('reservation.actions.failed')"
    >
      {{ pageError }}
    </InlineFeedback>
    <InlineFeedback
      v-if="outcome"
      tone="success"
      dismissible
      data-testid="reservation-list-outcome"
    >
      {{ outcome }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="reservation-list"
      server-side
      searchable
      filterable
      fill
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="guestOf"
      :card-icon="() => 'calendar-outline'"
      :entity-label="{ one: $t('reservation.list.entity.one'), many: $t('reservation.list.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('reservation.list.loadError') : undefined"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('reservation.list.search')"
      :labels="{ add: $t('reservation.list.new'), loadError: $t('reservation.list.loadError'), retry: $t('reservation.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="(row: ReservationOut) => canChange && openForm(row)"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #guest="{ row }">
        <span :class="{ 'reservation-list__erased': !row.guest_name }">{{ guestOf(row) }}</span>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="statusTone(row.status)"
          :label="$t(`reservation.status.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          v-if="table.filtered.value"
          data-testid="reservation-list-no-results"
          icon="search-outline"
          :heading="$t('reservation.list.noResultsTitle')"
          :message="$t('reservation.list.noResultsBody')"
        >
          <template #action>
            <ion-button
              size="small"
              fill="clear"
              data-testid="reservation-list-clear"
              @click="clearQuery"
            >
              {{ $t('reservation.list.clearFilters') }}
            </ion-button>
          </template>
        </EmptyState>
        <EmptyState
          v-else
          data-testid="reservation-list-empty"
          icon="calendar-outline"
          :heading="$t('reservation.list.emptyTitle')"
          :message="$t('reservation.list.emptyBody')"
        >
          <p class="reservation-list__hint">
            {{ $t('reservation.list.emptyHint') }}
          </p>
          <template
            v-if="canAdd"
            #action
          >
            <ion-button
              size="small"
              data-testid="reservation-list-empty-new"
              @click="openForm(null)"
            >
              {{ $t('reservation.list.new') }}
            </ion-button>
          </template>
        </EmptyState>
      </template>
    </DataTable>
    <ReservationFormModal
      v-model:open="formOpen"
      :reservation="editing"
      :day="day"
    />
    <StepDialog
      v-model:open="stepOpen"
      :kind="stepKind"
      :reservation="stepRow"
    />
  </AppPage>
</template>

<style scoped>
.reservation-list__erased {
  font-style: italic;
  color: var(--ion-color-medium, #8b897f);
}
.reservation-list__hint {
  margin: 4px 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
