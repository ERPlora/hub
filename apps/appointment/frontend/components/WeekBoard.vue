<script setup lang="ts">
// «By professional · Week» (APPOINTMENT-F27): a row per professional (the same lanes as the day, plus
// «Unassigned» when an appointment has nobody) and a column per day, Monday to Sunday, each day's
// appointments in order. Tapping an appointment opens it; the «+» of a day books on it with that
// professional; dragging an appointment (pointer events: a finger holds it first) to another day or row
// moves it keeping its time — never into the past. The page sends the move; the server decides.
import { HubIcon } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { dayOf, formatShortDay, formatTime, timeOf } from '../lib/clock';
import { allows, customerLabel } from '../lib/states';
import type { AppointmentRow, LaneOut } from '../operations';

const props = defineProps<{
  days: string[];
  lanes: LaneOut[];
  appointments: AppointmentRow[];
  now: Date;
  canBook: boolean;
  canMove: boolean;
}>();

const emit = defineEmits<{
  slot: [slot: { staffId: string | null; staffName: string; day: string }];
  open: [row: AppointmentRow];
  move: [move: { row: AppointmentRow; staffId: string | null; day: string }];
}>();

const t = useT();
const locale = useLocale();
const UNASSIGNED = 'unassigned';
const DRAG_THRESHOLD = 5;
const TOUCH_HOLD_MS = 400;
const TOUCH_TOLERANCE = 10;

const lanes = computed(() => {
  const out = props.lanes.map((lane) => ({ key: lane.staff_id, staffId: lane.staff_id as string | null, name: lane.name, takes: lane.takes_bookings }));
  if (props.appointments.some((row) => row.staff_id === null)) {
    out.push({ key: UNASSIGNED, staffId: null, name: t('appointment.grid.unassigned'), takes: false });
  }
  return out;
});

const cells = computed(() => {
  const out = new Map<string, AppointmentRow[]>();
  const sorted = [...props.appointments].sort((a, b) => a.start.localeCompare(b.start) || a.id.localeCompare(b.id));
  for (const row of sorted) {
    const key = `${row.staff_id ?? UNASSIGNED}|${dayOf(row.start)}`;
    out.set(key, [...(out.get(key) ?? []), row]);
  }
  return out;
});

const movable = (row: AppointmentRow): boolean => props.canMove && allows('edit', row, props.now);

interface Drag {
  row: AppointmentRow;
  startX: number;
  startY: number;
  active: boolean;
  held: boolean;
  timer: ReturnType<typeof setTimeout> | null;
}
const drag = ref<Drag | null>(null);
let swallowClick = false;

function onPointerDown(event: PointerEvent, row: AppointmentRow): void {
  if (!movable(row)) return;
  const touch = event.pointerType === 'touch';
  const state: Drag = { row, startX: event.clientX, startY: event.clientY, active: false, held: !touch, timer: null };
  if (touch) {
    state.timer = setTimeout(() => {
      if (drag.value === state) state.held = true;
    }, TOUCH_HOLD_MS);
  }
  drag.value = state;
  (event.target as Element & { setPointerCapture?: (id: number) => void }).setPointerCapture?.(event.pointerId);
}

function onPointerMove(event: PointerEvent): void {
  const state = drag.value;
  if (!state) return;
  const distance = Math.hypot(event.clientX - state.startX, event.clientY - state.startY);
  if (!state.held) {
    if (distance > TOUCH_TOLERANCE) cancelDrag();
    return;
  }
  if (distance >= DRAG_THRESHOLD) state.active = true;
}

function cancelDrag(): void {
  if (drag.value?.timer) clearTimeout(drag.value.timer);
  drag.value = null;
}

function onPointerUp(event: PointerEvent): void {
  const state = drag.value;
  cancelDrag();
  if (!state?.active) return;
  swallowClick = true;
  const cell = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-testid="appointment-week-cell"]');
  const lane = cell?.dataset.lane;
  const day = cell?.dataset.day;
  if (!lane || !day) return;
  const staffId = lane === UNASSIGNED ? null : lane;
  if (staffId === state.row.staff_id && day === dayOf(state.row.start)) return;
  const startsAt = new Date(`${day}T${timeOf(state.row.start)}:00${state.row.start.slice(19)}`);
  if (startsAt.getTime() < props.now.getTime()) return;
  emit('move', { row: state.row, staffId, day });
}

function onChipClick(row: AppointmentRow): void {
  if (swallowClick) {
    swallowClick = false;
    return;
  }
  emit('open', row);
}

function book(lane: { staffId: string | null; name: string; takes: boolean }, day: string): void {
  const bookable = lane.takes && lane.staffId !== null;
  emit('slot', { staffId: bookable ? lane.staffId : null, staffName: bookable ? lane.name : '', day });
}
</script>

<template>
  <div
    class="week-board"
    data-testid="appointment-week"
  >
    <table class="week-board__table">
      <thead>
        <tr>
          <th class="week-board__corner" />
          <th
            v-for="day in days"
            :key="day"
            scope="col"
            data-testid="appointment-week-day"
          >
            {{ formatShortDay(day, locale) }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="lane in lanes"
          :key="lane.key"
          data-testid="appointment-week-lane"
          :data-lane="lane.key"
        >
          <th
            scope="row"
            class="week-board__name"
            :class="{ 'week-board__name--kept': !lane.takes }"
          >
            {{ lane.name }}
          </th>
          <td
            v-for="day in days"
            :key="day"
            class="week-board__cell"
            data-testid="appointment-week-cell"
            :data-lane="lane.key"
            :data-day="day"
          >
            <button
              v-for="row in cells.get(`${lane.key}|${day}`) ?? []"
              :key="row.id"
              type="button"
              class="week-board__chip"
              :class="`week-board__chip--${row.status}`"
              data-testid="appointment-week-chip"
              :data-id="row.id"
              @pointerdown="onPointerDown($event, row)"
              @pointermove="onPointerMove"
              @pointerup="onPointerUp"
              @pointercancel="cancelDrag"
              @click="onChipClick(row)"
            >
              <strong>{{ formatTime(timeOf(row.start), locale) }}</strong> {{ customerLabel(row, t) }}
              <small>{{ row.service_names }}</small>
            </button>
            <button
              v-if="canBook"
              type="button"
              class="week-board__book"
              data-testid="appointment-week-book"
              :aria-label="t('appointment.grid.slot', { staff: lane.name, time: formatShortDay(day, locale) })"
              @click="book(lane, day)"
            >
              <HubIcon name="ion:add-outline" />
            </button>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.week-board {
  overflow-x: auto;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 10px;
}
.week-board__table {
  width: 100%;
  min-width: 860px;
  border-collapse: collapse;
  table-layout: fixed;
}
.week-board__table th,
.week-board__table td {
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
  border-left: 1px solid var(--ion-border-color, #e7e2d6);
  vertical-align: top;
}
.week-board__table thead th {
  padding: 8px 4px;
  font-size: 0.82rem;
  font-weight: 600;
  text-transform: capitalize;
}
.week-board__corner,
.week-board__name {
  width: 130px;
  position: sticky;
  left: 0;
  background: var(--ion-background-color, #fff);
  z-index: 1;
}
.week-board__name {
  padding: 8px;
  font-size: 0.86rem;
  text-align: left;
  font-weight: 500;
}
.week-board__name--kept {
  font-style: italic;
  color: var(--ion-color-medium, #6b7280);
}
.week-board__cell {
  padding: 4px;
  min-height: 64px;
}
.week-board__chip {
  display: block;
  width: 100%;
  margin-bottom: 4px;
  padding: 4px 6px;
  border: 0;
  border-left: 4px solid var(--ion-color-primary, #3880ff);
  border-radius: 6px;
  text-align: left;
  font-size: 0.76rem;
  line-height: 1.25;
  color: var(--ion-text-color, #1c1b17);
  background: color-mix(in srgb, var(--ion-color-primary, #3880ff) 14%, var(--ion-background-color, #fff));
  cursor: pointer;
  touch-action: pan-x pan-y;
}
.week-board__chip small {
  display: block;
  color: var(--ion-color-medium, #6b7280);
}
.week-board__chip--pending {
  border-left-color: var(--ion-color-warning, #ffc409);
}
.week-board__chip--completed {
  border-left-color: var(--ion-color-success, #2dd36f);
}
.week-board__chip--cancelled,
.week-board__chip--no_show {
  opacity: 0.55;
  text-decoration: line-through;
}
.week-board__book {
  width: 100%;
  min-height: 24px;
  border: 1px dashed transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--ion-color-medium, #6b7280);
  cursor: pointer;
}
.week-board__book:hover,
.week-board__book:focus-visible {
  border-color: var(--ion-color-primary, #3880ff);
  color: var(--ion-color-primary, #3880ff);
}
</style>
