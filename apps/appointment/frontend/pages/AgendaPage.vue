<script setup lang="ts">
// Appointments → Agenda (WORKBOOK «Pantallas · Agenda»): the bar (day or week, status filter, «N to
// confirm», «List · By professional · Repeating», «Day · Week») and the view, all live and on the
// business's clock (its zone comes with the settings). The page follows the range's appointments — every
// one of them, in windows of 100 —, the agenda's rows (`appointment.agenda.lanes`), the blocks and the
// bookings to confirm. «Add appointment» and a tapped slot open the booking panel; an appointment opens
// its panel (or its history once it can no longer move); a drag moves it; the row actions run
// (`useAgendaActions`). An employee sees her own agenda, and is told when her account has no record. The address
// may name the day (`?date=YYYY-MM-DD`: a tap on the device's notice of a booking, APPOINTMENT-F28).
import { ConfirmDialog, InlineFeedback } from '@erplora/ui/components';
import { useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue';
import { useRoute } from 'vue-router';

import AgendaToolbar, { type AgendaSpan, type AgendaView } from '../components/AgendaToolbar.vue';
import AppointmentFormModal, { type BookingPreset } from '../components/AppointmentFormModal.vue';
import AppointmentList from '../components/AppointmentList.vue';
import CancelDialog from '../components/CancelDialog.vue';
import DayGrid from '../components/DayGrid.vue';
import HistoryModal from '../components/HistoryModal.vue';
import PageNotices from '../components/PageNotices.vue';
import SeriesList from '../components/SeriesList.vue';
import WeekBoard from '../components/WeekBoard.vue';
import { useAgendaActions } from '../composables/useAgendaActions';
import { useLiveWindows } from '../composables/useLiveWindows';
import { useT } from '../composables/useT';
import { todayIn, wallInput, wallNowIn, weekDays } from '../lib/clock';
import { allows } from '../lib/states';
import type { AppointmentOut, AppointmentRow, AppointmentStatus } from '../operations';
import { appointmentTabs } from '../tabs';

/** The zone until the settings say the business's (phase 1: Europe/Madrid, as the server). */
const FALLBACK_ZONE = 'Europe/Madrid';
/** The most appointments a range paints (ten windows of 100). */
const MAX_ROWS = 1000;

const t = useT();
const session = useSession();
const client = useLiveClient();

const { data: settings } = useLive('appointment.settings.get', {});
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
const businessNow = computed(() => wallNowIn(zone.value, clock.value));

const day = ref(todayIn(FALLBACK_ZONE));
const dayTouched = ref(false);
watch(zone, () => {
  if (!dayTouched.value) day.value = today.value;
});
function setDay(value: string): void {
  dayTouched.value = true;
  day.value = value;
}
/** The day the address names (`?date=`), when it is a real date. */
function askedDay(value: unknown): string | null {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : null;
}
const route = useRoute();
watch(
  () => route.query.date,
  (value) => {
    const asked = askedDay(value);
    if (asked) setDay(asked);
  },
  { immediate: true },
);
const view = ref<AgendaView>('list');
const span = ref<AgendaSpan>('day');
const status = ref('');

const days = computed(() => (span.value === 'week' ? weekDays(day.value) : [day.value]));
const range = computed(() => ({ date_from: days.value[0], date_to: days.value[days.value.length - 1] }));

const wanted = ref(100);
const list = useLiveWindows<'appointment.appointment.list', AppointmentRow>(
  'appointment.appointment.list',
  () => ({ ...range.value, sort: 'start', ...(status.value ? { status: status.value as AppointmentStatus } : {}) }),
  100,
  { start: () => 0, rows: () => wanted.value },
);
watch(
  () => list.total.value,
  (total) => {
    wanted.value = Math.min(MAX_ROWS, Math.max(100, total ?? 100));
  },
);

const lanes = useLive('appointment.agenda.lanes', range);
const blocks = useLive(
  'appointment.blocked_time.list',
  computed(() => ({ ...range.value, limit: 100 })),
);
const { data: toConfirm } = useLive('appointment.appointment.count_to_confirm', {});
/** The business's hours of the range (Schedules): the day grid shades what is closed. */
const hours = useLive('schedule.hours.for_range', range);
const dayHours = computed(() => hours.data.value?.days.find((entry) => entry.date === day.value) ?? null);

const ownLane = computed(() => lanes.data.value?.rows.find((lane) => lane.staff_id === lanes.data.value?.own_staff_id) ?? null);
const ownLinked = computed(() => !!lanes.data.value?.own_staff_id);
const notLinked = computed(() => lanes.data.value !== undefined && !lanes.data.value.sees_everyone && !ownLinked.value);
const canAdd = computed(
  () => session.can('appointment.add_appointment') || (session.can('appointment.add_own_appointment') && ownLinked.value),
);
const canChange = computed(
  () => session.can('appointment.change_appointment') || (session.can('appointment.change_own_appointment') && ownLinked.value),
);
const canDelete = computed(() => session.can('appointment.delete_appointment'));
const ownStaff = computed(() =>
  !session.can('appointment.add_appointment') && ownLane.value ? { id: ownLane.value.staff_id, name: ownLane.value.name } : null,
);

// The booking panel
const formOpen = ref(false);
const editing = shallowRef<AppointmentOut | null>(null);
const preset = shallowRef<BookingPreset | null>(null);

function openNew(next: BookingPreset | null = null): void {
  editing.value = null;
  preset.value = next ?? { day: day.value };
  formOpen.value = true;
}

const actions = useAgendaActions({
  onEdit: async (row: AppointmentRow) => {
    try {
      editing.value = await client.api.call('appointment.appointment.get', { id: row.id });
    } catch (error) {
      actions.notice.value = { tone: 'danger', text: (error as Error).message };
      return;
    }
    preset.value = null;
    formOpen.value = true;
  },
});

function openRow(row: AppointmentRow): void {
  void actions.run(canChange.value && allows('edit', row, clock.value) ? 'edit' : 'history', row);
}

function onSlot(slot: { staffId: string | null; staffName: string; time?: string; day?: string }): void {
  openNew({ day: slot.day ?? day.value, time: slot.time, staffId: slot.staffId, staffName: slot.staffName });
}

function onMove(move: { row: AppointmentRow; staffId: string | null; time?: string; day?: string }): void {
  // The day grid moves within its day; the week board keeps the time and changes the day.
  const when = wallInput(move.day ?? day.value, move.time ?? move.row.start.slice(11, 16));
  void actions.move(move.row, { start: when, staffId: move.staffId });
}

function onOutcome(text: string): void {
  actions.notice.value = { tone: 'success', text };
}

const tabs = computed(() => appointmentTabs(t, { settings: session.can('appointment.manage_settings') }));
const listError = computed(() => (list.status.value === 'error' ? t('appointment.list.loadError') : undefined));
</script>

<template>
  <AppPage
    :title="$t('appointment.title')"
    content-layout="fill"
    :tabs="tabs"
    :tabs-label="$t('appointment.tabs.label')"
  >
    <PageNotices
      testid="appointment-agenda"
      :status="list.status.value"
      :error="list.error.value"
    />
    <AgendaToolbar
      :day="day"
      :view="view"
      :span="span"
      :status="status"
      :to-confirm="toConfirm?.count ?? 0"
      :today="today"
      :zone="zone"
      @update:day="setDay"
      @update:view="view = $event"
      @update:span="span = $event"
      @update:status="status = $event"
    />
    <InlineFeedback
      v-if="notLinked"
      tone="warning"
      data-testid="appointment-agenda-not-linked"
    >
      {{ $t('appointment.grid.notLinked') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="(lanes.data.value?.unassigned ?? 0) > 0 && view !== 'series'"
      tone="warning"
      data-testid="appointment-agenda-unassigned"
    >
      {{ t('appointment.grid.unassignedWarning', { n: lanes.data.value?.unassigned ?? 0 }) }}
    </InlineFeedback>
    <InlineFeedback
      v-if="actions.notice.value"
      :tone="actions.notice.value.tone"
      dismissible
      data-testid="appointment-agenda-notice"
      @dismiss="actions.notice.value = null"
    >
      {{ actions.notice.value.text }}
    </InlineFeedback>

    <AppointmentList
      v-if="view === 'list'"
      :rows="list.rows.value"
      :now="clock"
      :can-add="canAdd"
      :can-delete="canDelete"
      :loading="list.status.value === 'loading'"
      :error="listError"
      :with-day="span === 'week'"
      :empty-message="span === 'week' ? $t('appointment.list.emptyWeek') : undefined"
      @action="actions.run($event.actionId, $event.row)"
      @add="openNew()"
      @retry="list.refresh()"
    />

    <template v-else-if="view === 'staff'">
      <div
        v-if="lanes.status.value === 'loading' && !lanes.data.value"
        class="agenda__state"
        data-testid="appointment-agenda-lanes-loading"
      >
        <ion-spinner name="dots" />{{ $t('appointment.grid.staffLoading') }}
      </div>
      <InlineFeedback
        v-else-if="lanes.status.value === 'error'"
        tone="danger"
        data-testid="appointment-agenda-lanes-error"
      >
        {{ $t('appointment.grid.staffError') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            @click="lanes.refresh()"
          >
            {{ $t('appointment.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <template v-else>
        <p
          v-if="!lanes.data.value?.rows.length && !notLinked"
          class="agenda__state"
          data-testid="appointment-agenda-no-staff"
        >
          {{ $t('appointment.grid.noStaff') }}
        </p>
        <div
          v-if="canAdd"
          class="agenda__add"
        >
          <ion-button
            size="small"
            data-testid="appointment-agenda-add"
            @click="openNew()"
          >
            {{ $t('appointment.toolbar.add') }}
          </ion-button>
        </div>
        <DayGrid
          v-if="span === 'day'"
          :day="day"
          :hours="dayHours"
          :lanes="lanes.data.value?.rows ?? []"
          :appointments="list.rows.value"
          :blocks="blocks.data.value?.rows ?? []"
          :start-hour="settings?.calendar_start_hour ?? 8"
          :end-hour="settings?.calendar_end_hour ?? 20"
          :slot-interval="settings?.slot_interval ?? 15"
          :now="clock"
          :can-book="canAdd"
          :can-move="canChange"
          @slot="onSlot"
          @open="openRow"
          @move="onMove"
        />
        <WeekBoard
          v-else
          :days="days"
          :lanes="lanes.data.value?.rows ?? []"
          :appointments="list.rows.value"
          :now="clock"
          :can-book="canAdd"
          :can-move="canChange"
          @slot="onSlot"
          @open="openRow"
          @move="onMove"
        />
      </template>
    </template>

    <SeriesList
      v-else
      :can-add="canAdd"
      :can-change="canChange"
      :business-today="today"
      :own-staff="ownStaff"
    />

    <AppointmentFormModal
      v-model:open="formOpen"
      :appointment="editing"
      :preset="preset"
      :own-staff="ownStaff"
      :business-now="businessNow"
      @outcome="onOutcome"
    />
    <CancelDialog
      v-model:open="actions.cancelOpen.value"
      :appointment="actions.target.value"
    />
    <HistoryModal
      v-model:open="actions.historyOpen.value"
      :appointment="actions.target.value"
    />
    <ConfirmDialog
      v-model:open="actions.deleteOpen.value"
      testid="appointment-delete"
      tone="danger"
      :title="t('appointment.deleteDialog.title')"
      :message="t('appointment.deleteDialog.message', { number: actions.target.value?.number ?? '' })"
      :confirm-label="t('appointment.deleteDialog.confirm')"
      :cancel-label="t('appointment.cancelDialog.keep')"
      :pending="actions.deleting.pending.value"
      :error="actions.deleting.error.value"
      @confirm="actions.confirmDelete()"
      @cancel="actions.deleteOpen.value = false"
    />
    <ConfirmDialog
      :open="actions.overlap.value !== null"
      testid="appointment-move-overlap"
      tone="warning"
      :title="t('appointment.overlap.title')"
      :message="actions.overlap.value ?? ''"
      :confirm-label="t('appointment.overlap.confirm')"
      :cancel-label="t('appointment.overlap.cancel')"
      @update:open="(value: boolean) => !value && (actions.overlap.value = null)"
      @confirm="actions.confirmOverlap()"
      @cancel="actions.overlap.value = null"
    />
  </AppPage>
</template>

<style scoped>
.agenda__state {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ion-color-medium, #6b7280);
}
.agenda__add {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}
</style>
