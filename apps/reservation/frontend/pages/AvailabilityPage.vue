<script setup lang="ts">
// Reservations → Availability (WORKBOOK «Pantallas · Disponibilidad»; RESERVATION-F01, F02, F05): three
// stacked sections, each with its own loading, error and empty state.
// - Occupancy: a date (today on the business's clock) with the opening hours of Schedules and the day's
//   blocks above, and per slot (live `reservation.availability.day`, the gate's own count) Slot, Reserved,
//   Max, Guests and Available — a full one dimmed with «Full» (OpenTable, Resy: visible, not hidden), one
//   that starts with the business closed marked «Outside opening hours».
// - Time slots: the live `reservation.time_slot.list` — Day, From, To, Max, Max guests; «Add slot» and
//   «Remove» (asks first) for whoever may change them.
// - Blocked dates: the live `reservation.blocked_date.list` — Date, Reason, Full day (or its hours);
//   «Add blocked date» and «Remove» (asks first).
import {
  ConfirmDialog,
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
import { IonInput } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import BlockedDateFormModal from '../components/BlockedDateFormModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import SlotFormModal from '../components/SlotFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatShortDate, formatTime, todayIn, weekdayOf } from '../lib/clock';
import { spansLine } from '../lib/states';
import { WEEKDAYS, weekdayKey } from '../lib/weekdays';
import type { BlockedDateOut, SlotLoadOut, TimeSlotOut } from '../operations';
import { reservationTabs } from '../tabs';

const FALLBACK_ZONE = 'Europe/Madrid';

const session = useSession();
const t = useT();
const locale = useLocale();
const canSlots = computed(() => session.can('reservation.change_timeslot'));
const canBlocked = computed(() => session.can('reservation.change_blockeddate'));

const { data: settings } = useLive('reservation.settings.get', {});
const day = ref(todayIn(FALLBACK_ZONE));
const dayTouched = ref(false);
const zone = computed(() => settings.value?.timezone ?? FALLBACK_ZONE);
function setDay(value: string): void {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value === day.value) return;
  dayTouched.value = true;
  day.value = value;
}
const today = computed(() => todayIn(zone.value));
watch(today, (value) => {
  if (!dayTouched.value) day.value = value;
});

// ── Occupancy ───────────────────────────────────────────────────────────────────────────────────

const occupancy = useLive('reservation.availability.day', () => ({ date: day.value }));
const figures = computed(() => occupancy.data.value);
const time = (hhmm: string): string => formatTime(hhmm, locale.value);
const hoursLine = computed(() => {
  const now = figures.value;
  if (!now) return '';
  if (!now.hours_restricted) return t('reservation.availability.noHours');
  if (!now.spans.length) return t('reservation.availability.closedBySchedule');
  return t('reservation.availability.hours', { spans: spansLine(now.spans, time) });
});
const blocksLine = computed(() =>
  (figures.value?.blocks ?? [])
    .map((block) =>
      block.is_full_day
        ? t('reservation.availability.blockedDay', { reason: block.reason || '—' })
        : t('reservation.availability.blockedHours', {
            from: time(block.blocked_from ?? ''),
            to: time(block.blocked_until ?? ''),
            reason: block.reason || '—',
          }),
    )
    .join(' · '),
);

// The slots go by their start, as the server gives them: no sorting, as the old occupancy table.
const occupancyColumns = computed<DataTableColumn<SlotLoadOut>[]>(() => [
  { key: 'slot', label: t('reservation.availability.columns.slot'), cell: 'slot', priority: 'high', sortable: false },
  { key: 'reserved', label: t('reservation.availability.columns.reserved'), align: 'right', cell: 'reserved', sortable: false },
  { key: 'max_reservations', label: t('reservation.availability.columns.max'), align: 'right', cell: 'max', sortable: false },
  { key: 'covers', label: t('reservation.availability.columns.covers'), align: 'right', cell: 'covers', sortable: false },
  { key: 'available', label: t('reservation.availability.columns.available'), align: 'right', cell: 'available', sortable: false },
]);

// ── Time slots ──────────────────────────────────────────────────────────────────────────────────

const slotsTable = useServerTable({ sort: 'day_of_week' });
const slotFilters = ref<DataTableFilters>({});
const slots = useLiveList(
  'reservation.time_slot.list',
  () => ({
    ...(slotFilters.value.day_of_week ? { day_of_week: Number(slotFilters.value.day_of_week) } : {}),
    sort: slotsTable.query.value.sort,
  }),
  () => slotsTable.windows.value,
);
slotsTable.followResult(slots.data);
function onSlotFilters(next: DataTableFilters): void {
  slotFilters.value = next;
  slotsTable.restart({ narrowed: Object.keys(next).length > 0 });
}

const slotColumns = computed<DataTableColumn<TimeSlotOut>[]>(() => [
  {
    key: 'day_of_week',
    label: t('reservation.availability.columns.day'),
    sortable: true,
    format: (_, row) => t(weekdayKey(row.day_of_week)),
    filter: { type: 'select', options: WEEKDAYS.map((name, index) => ({ value: String(index), label: t(`reservation.weekday.${name}`) })) },
  },
  { key: 'start_time', label: t('reservation.availability.columns.from'), sortable: true, format: (_, row) => time(row.start_time) },
  { key: 'end_time', label: t('reservation.availability.columns.to'), sortable: true, format: (_, row) => time(row.end_time) },
  {
    key: 'max_reservations',
    label: t('reservation.availability.columns.maxReservations'),
    sortable: true,
    align: 'right',
    format: (_, row) => String(row.max_reservations),
  },
  {
    key: 'max_covers',
    label: t('reservation.availability.columns.maxCovers'),
    align: 'right',
    format: (_, row) => (row.max_covers === null ? t('reservation.availability.noLimit') : String(row.max_covers)),
  },
]);

// ── Blocked dates ───────────────────────────────────────────────────────────────────────────────

const blockedTable = useServerTable({ sort: 'date' });
const blockedFilters = ref<DataTableFilters>({});
const blocked = useLiveList(
  'reservation.blocked_date.list',
  () => ({
    ...(blockedFilters.value.date ? { date_from: blockedFilters.value.date, date_to: blockedFilters.value.date } : {}),
    ...(blockedFilters.value.is_full_day ? { is_full_day: blockedFilters.value.is_full_day === 'true' } : {}),
    sort: blockedTable.query.value.sort,
  }),
  () => blockedTable.windows.value,
);
blockedTable.followResult(blocked.data);
function onBlockedFilters(next: DataTableFilters): void {
  blockedFilters.value = next;
  blockedTable.restart({ narrowed: Object.keys(next).length > 0 });
}

const hoursOf = (row: BlockedDateOut): string =>
  row.is_full_day ? t('reservation.availability.wholeDay') : `${time(row.blocked_from ?? '')}–${time(row.blocked_until ?? '')}`;

const blockedColumns = computed<DataTableColumn<BlockedDateOut>[]>(() => [
  {
    key: 'date',
    label: t('reservation.availability.columns.date'),
    sortable: true,
    format: (_, row) => formatShortDate(row.date, locale.value),
    filter: { type: 'date' },
  },
  { key: 'reason', label: t('reservation.availability.columns.reason'), sortable: true, priority: 'high' },
  {
    key: 'is_full_day',
    label: t('reservation.availability.columns.hours'),
    sortable: true,
    format: (_, row) => hoursOf(row),
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('reservation.yes') },
        { value: 'false', label: t('reservation.no') },
      ],
    },
  },
]);

// ── Removing, adding ────────────────────────────────────────────────────────────────────────────

const removeAction = computed(() => ({ id: 'remove', label: t('reservation.availability.remove'), icon: 'trash-outline', color: 'danger' }));
const slotActions = computed<DataTableAction<TimeSlotOut>[]>(() => (canSlots.value ? [removeAction.value] : []));
const blockedActions = computed<DataTableAction<BlockedDateOut>[]>(() => (canBlocked.value ? [removeAction.value] : []));

const removeSlot = useCommand('reservation.time_slot.delete');
const removeBlocked = useCommand('reservation.blocked_date.delete');
const slotGoing = shallowRef<TimeSlotOut | null>(null);
const blockedGoing = shallowRef<BlockedDateOut | null>(null);
const slotFormOpen = ref(false);
const blockedFormOpen = ref(false);
const pageError = ref<string | null>(null);

async function confirmRemoveSlot(): Promise<void> {
  const row = slotGoing.value;
  if (!row) return;
  pageError.value = null;
  try {
    await removeSlot.run({ id: row.id });
    slotGoing.value = null;
  } catch (caught) {
    slotGoing.value = null;
    pageError.value = (caught as Error)?.message || t('reservation.availability.removeFailed');
  }
}

async function confirmRemoveBlocked(): Promise<void> {
  const row = blockedGoing.value;
  if (!row) return;
  pageError.value = null;
  try {
    await removeBlocked.run({ id: row.id });
    blockedGoing.value = null;
  } catch (caught) {
    blockedGoing.value = null;
    pageError.value = (caught as Error)?.message || t('reservation.availability.removeFailed');
  }
}

const slotMessage = computed(() => {
  const row = slotGoing.value;
  return row
    ? t('reservation.availability.removeSlot.message', { day: t(weekdayKey(row.day_of_week)), from: time(row.start_time), to: time(row.end_time) })
    : '';
});
const blockedMessage = computed(() =>
  blockedGoing.value ? t('reservation.availability.removeBlocked.message', { date: formatShortDate(blockedGoing.value.date, locale.value) }) : '',
);

const noticeStatus = computed(() => occupancy.status.value);
const noticeError = computed(() => occupancy.error.value ?? slots.error.value ?? blocked.error.value);
const isBlocked = computed(() => blockingError(noticeError.value));
</script>

<template>
  <AppPage
    :title="$t('reservation.title')"
    :tabs="reservationTabs($t, { settings: session.can('reservation.manage_settings') })"
    :tabs-label="$t('reservation.tabs.label')"
  >
    <PageNotices
      testid="reservation-availability"
      :status="noticeStatus"
      :error="noticeError"
    />
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      dismissible
      data-testid="reservation-availability-page-error"
      :heading="$t('reservation.availability.removeFailed')"
    >
      {{ pageError }}
    </InlineFeedback>
    <template v-if="!isBlocked">
      <section class="reservation-availability__section">
        <h3>{{ $t('reservation.availability.occupancy') }}</h3>
        <div class="reservation-availability__bar">
          <ion-input
            class="reservation-availability__date"
            data-testid="reservation-availability-date"
            type="date"
            :value="day"
            :label="$t('reservation.availability.date')"
            label-placement="floating"
            fill="outline"
            mode="md"
            @ion-change="setDay(String($event.detail.value ?? ''))"
          />
          <div class="reservation-availability__notes">
            <p
              v-if="hoursLine"
              data-testid="reservation-availability-hours"
            >
              {{ hoursLine }}
            </p>
            <p
              v-if="blocksLine"
              class="reservation-availability__blocked"
              data-testid="reservation-availability-blocks"
            >
              {{ blocksLine }}
            </p>
          </div>
        </div>
        <DataTable
          testid="reservation-availability-occupancy"
          row-key="id"
          :rows="figures?.slots ?? []"
          :columns="occupancyColumns"
          :page-size="50"
          :loading="occupancy.status.value === 'loading'"
          :error="occupancy.status.value === 'error' ? $t('reservation.availability.occupancyError') : undefined"
          :labels="{ loadError: $t('reservation.availability.occupancyError'), retry: $t('reservation.retry') }"
          :empty-message="$t('reservation.availability.emptyOccupancy')"
          @retry="occupancy.refresh()"
        >
          <template #slot="{ row }">
            <span :class="{ 'reservation-availability__full': row.full }">{{ time(row.start_time) }}–{{ time(row.end_time) }}</span>
          </template>
          <template #reserved="{ row }">
            <span :class="{ 'reservation-availability__full': row.full }">{{ row.reserved }}</span>
          </template>
          <template #max="{ row }">
            <span :class="{ 'reservation-availability__full': row.full }">{{ row.max_reservations }}</span>
          </template>
          <template #covers="{ row }">
            <span :class="{ 'reservation-availability__full': row.full }">{{ row.max_covers === null ? row.covers : `${row.covers} / ${row.max_covers}` }}</span>
          </template>
          <template #available="{ row }">
            <StatusPill
              v-if="row.full"
              size="sm"
              tone="danger"
              :label="$t('reservation.availability.full')"
            /><strong v-else>{{ row.available }}</strong>{{ row.in_hours ? '' : ' ' }}<StatusPill
              v-if="!row.in_hours"
              size="sm"
              tone="warning"
              :label="$t('reservation.availability.outside')"
            />
          </template>
          <template #empty>
            <EmptyState
              icon="time-outline"
              :heading="$t('reservation.availability.emptyOccupancy')"
            />
          </template>
        </DataTable>
      </section>

      <section class="reservation-availability__section">
        <h3>{{ $t('reservation.availability.slots') }}</h3>
        <DataTable
          testid="reservation-availability-slots"
          server-side
          filterable
          :filters="slotFilters"
          :rows="slots.data.value?.rows ?? []"
          :total="slots.data.value?.total ?? 0"
          :page="slotsTable.page.value"
          :page-size="slotsTable.pageSize.value"
          :sort="slotsTable.sort.value"
          :sort-dir="slotsTable.dir.value"
          :views="['table', 'cards']"
          :card-title="(row: TimeSlotOut) => `${t(weekdayKey(row.day_of_week))} · ${time(row.start_time)}`"
          :entity-label="{ one: $t('reservation.availability.slotEntity.one'), many: $t('reservation.availability.slotEntity.many') }"
          :loading="slots.status.value === 'loading'"
          :error="slots.status.value === 'error' ? $t('reservation.availability.slotsError') : undefined"
          :addable="canSlots"
          :actions="slotActions"
          :labels="{ add: $t('reservation.availability.addSlot'), loadError: $t('reservation.availability.slotsError'), retry: $t('reservation.retry') }"
          :columns="slotColumns"
          @filters-change="onSlotFilters"
          @page-change="slotsTable.goToPage"
          @load-more="slotsTable.loadMore"
          @page-size-change="slotsTable.setPageSize"
          @sort-change="slotsTable.setSort"
          @add="slotFormOpen = true"
          @action="({ row }: { row: TimeSlotOut }) => (slotGoing = row)"
          @retry="slots.refresh()"
        >
          <template #empty>
            <EmptyState
              icon="time-outline"
              :heading="$t('reservation.availability.emptySlots')"
            />
          </template>
        </DataTable>
      </section>

      <section class="reservation-availability__section">
        <h3>{{ $t('reservation.availability.blocked') }}</h3>
        <DataTable
          testid="reservation-availability-blocked"
          server-side
          filterable
          :filters="blockedFilters"
          :rows="blocked.data.value?.rows ?? []"
          :total="blocked.data.value?.total ?? 0"
          :page="blockedTable.page.value"
          :page-size="blockedTable.pageSize.value"
          :sort="blockedTable.sort.value"
          :sort-dir="blockedTable.dir.value"
          :views="['table', 'cards']"
          :card-title="(row: BlockedDateOut) => formatShortDate(row.date, locale)"
          :entity-label="{ one: $t('reservation.availability.blockedEntity.one'), many: $t('reservation.availability.blockedEntity.many') }"
          :loading="blocked.status.value === 'loading'"
          :error="blocked.status.value === 'error' ? $t('reservation.availability.blockedError') : undefined"
          :addable="canBlocked"
          :actions="blockedActions"
          :labels="{ add: $t('reservation.availability.addBlocked'), loadError: $t('reservation.availability.blockedError'), retry: $t('reservation.retry') }"
          :columns="blockedColumns"
          @filters-change="onBlockedFilters"
          @page-change="blockedTable.goToPage"
          @load-more="blockedTable.loadMore"
          @page-size-change="blockedTable.setPageSize"
          @sort-change="blockedTable.setSort"
          @add="blockedFormOpen = true"
          @action="({ row }: { row: BlockedDateOut }) => (blockedGoing = row)"
          @retry="blocked.refresh()"
        >
          <template #empty>
            <EmptyState
              icon="calendar-outline"
              :heading="$t('reservation.availability.emptyBlocked')"
            />
          </template>
        </DataTable>
      </section>
    </template>
    <SlotFormModal
      v-model:open="slotFormOpen"
      :weekday="weekdayOf(day)"
    />
    <BlockedDateFormModal
      v-model:open="blockedFormOpen"
      :day="day"
    />
    <ConfirmDialog
      :open="slotGoing !== null"
      testid="reservation-availability-remove-slot"
      tone="danger"
      :title="t('reservation.availability.removeSlot.title')"
      :message="slotMessage"
      :confirm-label="t('reservation.availability.removeSlot.confirm')"
      :cancel-label="t('reservation.cancelButton')"
      :pending="removeSlot.pending.value"
      @update:open="(value: boolean) => !value && (slotGoing = null)"
      @confirm="confirmRemoveSlot"
      @cancel="slotGoing = null"
    />
    <ConfirmDialog
      :open="blockedGoing !== null"
      testid="reservation-availability-remove-blocked"
      tone="danger"
      :title="t('reservation.availability.removeBlocked.title')"
      :message="blockedMessage"
      :confirm-label="t('reservation.availability.removeBlocked.confirm')"
      :cancel-label="t('reservation.cancelButton')"
      :pending="removeBlocked.pending.value"
      @update:open="(value: boolean) => !value && (blockedGoing = null)"
      @confirm="confirmRemoveBlocked"
      @cancel="blockedGoing = null"
    />
  </AppPage>
</template>

<style scoped>
.reservation-availability__section {
  margin-bottom: 20px;
}
.reservation-availability__section h3 {
  margin: 16px 0 8px;
  font-size: 1rem;
}
.reservation-availability__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 8px;
}
.reservation-availability__date {
  max-width: 12rem;
  --min-height: 44px;
}
.reservation-availability__notes p {
  margin: 0;
  font-size: 0.9rem;
}
.reservation-availability__blocked {
  color: var(--ion-color-danger, #eb445a);
  font-weight: 600;
}
.reservation-availability__full {
  opacity: 0.55;
}
</style>
