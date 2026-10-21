<script setup lang="ts">
// «By professional · Day» (APPOINTMENT-F01, F04, F25): the old `ok-scheduler` timeline, as our own grid
// until @erplora/ui has its `Scheduler` (asked in UI-REQUESTS.md). A row per bookable professional, then
// whoever no longer takes bookings but keeps appointments that day (warned above: their appointments stay
// on their row to be handed over), then «Unassigned» when an appointment has nobody; the calendar
// window's hours across, the blocked periods and the hours the business is closed (Schedules) painted.
//   - Tapping a free slot books there: that professional and time (on a row that takes no bookings, or
//     «Unassigned», only the time). Each slot is a button with its own name, so the keyboard books too.
//     A closed hour has no slot to tap.
//   - Tapping an appointment opens it (a button: Enter and Space as well).
//   - Dragging one moves it to another time or row — pointer events, so mouse, pen and finger alike; a
//     finger must hold it first (400 ms), as Vagaro asks, or a scroll would move a customer's booking. It
//     snaps to the slot interval, never lands in the past or outside the window, and only what may still
//     move (pending or confirmed, not charged) drags. The page sends the move; the server decides.
import type { OutputOf } from '@erplora/ui/sdk';
import { computed, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatTime, minutesOf } from '../lib/clock';
import { allows, customerLabel } from '../lib/states';
import type { AppointmentRow, BlockedTimeOut, LaneOut } from '../operations';

/** The day's hours from Schedules (`schedule.hours.for_range`). */
export type DayHours = OutputOf<'schedule.hours.for_range'>['days'][number];

const props = defineProps<{
  day: string;
  /** The day's hours (Schedules): what is closed is shaded and books nothing; `null` = not known yet. */
  hours?: DayHours | null;
  lanes: LaneOut[];
  appointments: AppointmentRow[];
  blocks: BlockedTimeOut[];
  startHour: number;
  endHour: number;
  slotInterval: number;
  now: Date;
  /** May book: the free slots are buttons. */
  canBook: boolean;
  /** May move appointments (each one also has to allow it). */
  canMove: boolean;
}>();

const emit = defineEmits<{
  slot: [slot: { staffId: string | null; staffName: string; time: string }];
  open: [row: AppointmentRow];
  move: [move: { row: AppointmentRow; staffId: string | null; time: string }];
}>();

const t = useT();
const locale = useLocale();

/** 96 px an hour, 56 px a row: the old scheduler's proportions. */
const PX_PER_MINUTE = 1.6;
const LANE_HEIGHT = 56;
const DRAG_THRESHOLD = 5;
const TOUCH_HOLD_MS = 400;
const TOUCH_TOLERANCE = 10;
const UNASSIGNED = 'unassigned';

const windowStart = computed(() => props.startHour * 60);
const windowEnd = computed(() => props.endHour * 60);
const width = computed(() => (windowEnd.value - windowStart.value) * PX_PER_MINUTE);
const hours = computed(() => Array.from({ length: props.endHour - props.startHour }, (_, i) => props.startHour + i));

interface Lane {
  key: string;
  staffId: string | null;
  name: string;
  color: string;
  takesBookings: boolean;
}

const lanes = computed<Lane[]>(() => {
  const out: Lane[] = props.lanes.map((lane) => ({
    key: lane.staff_id,
    staffId: lane.staff_id,
    name: lane.name,
    color: lane.color,
    takesBookings: lane.takes_bookings,
  }));
  if (props.appointments.some((row) => row.staff_id === null)) {
    out.push({ key: UNASSIGNED, staffId: null, name: t('appointment.grid.unassigned'), color: '', takesBookings: false });
  }
  return out;
});

const kept = computed(() => props.lanes.filter((lane) => !lane.takes_bookings).map((lane) => lane.name));
const keptMessage = computed(() => {
  if (!kept.value.length) return '';
  const names = new Intl.ListFormat(locale.value, { type: 'conjunction' }).format(kept.value);
  return t(kept.value.length === 1 ? 'appointment.grid.keptOne' : 'appointment.grid.keptMany', { names });
});

const pad = (n: number): string => String(n).padStart(2, '0');
const hhmm = (minute: number): string => `${pad(Math.floor(minute / 60))}:${pad(minute % 60)}`;

/** Minute of the day of a wall-clock `YYYY-MM-DDTHH:MM`: 0 before the day, 1440 after it. */
function minuteOfDay(wall: string): number {
  const date = wall.slice(0, 10);
  if (date < props.day) return 0;
  if (date > props.day) return 24 * 60;
  return Number(wall.slice(11, 13)) * 60 + Number(wall.slice(14, 16));
}

/** The closed periods of the day, `[from, to)` in minutes: around and between its opening spans, the
 *  whole day when it is closed, nothing without a rule of hours (the business never refuses then). */
const closed = computed<Array<[number, number]>>(() => {
  const hours = props.hours;
  if (!hours || hours.source === 'none') return [];
  const spans = hours.is_closed ? [] : hours.spans.map((span) => [minuteOfDay(span.start), minuteOfDay(span.end)] as const);
  const out: Array<[number, number]> = [];
  let from = 0;
  for (const [open, close] of [...spans].sort((a, b) => a[0] - b[0])) {
    if (open > from) out.push([from, open]);
    from = Math.max(from, close);
  }
  if (from < 24 * 60) out.push([from, 24 * 60]);
  return out;
});

const isClosed = (minute: number): boolean => closed.value.some(([from, to]) => minute >= from && minute < to);

const closedSpans = computed(() =>
  closed.value.flatMap(([from, to]) => {
    const span = horizontal(from, to - from);
    return span ? [{ key: from, ...span }] : [];
  }),
);

const slots = computed(() => {
  const step = Math.max(5, props.slotInterval);
  const out: number[] = [];
  for (let minute = windowStart.value; minute < windowEnd.value; minute += step) if (!isClosed(minute)) out.push(minute);
  return out;
});

function laneKeyOf(row: AppointmentRow): string {
  return row.staff_id ?? UNASSIGNED;
}

/** Each appointment of a row in a track of its own while it overlaps another. */
const placed = computed(() => {
  const out = new Map<string, { top: number; height: number }>();
  for (const lane of lanes.value) {
    const rows = props.appointments
      .filter((row) => laneKeyOf(row) === lane.key)
      .sort((a, b) => a.start.localeCompare(b.start) || a.id.localeCompare(b.id));
    const ends: number[] = [];
    const tracks = new Map<string, number>();
    for (const row of rows) {
      const start = minutesOf(row.start);
      let track = ends.findIndex((end) => end <= start);
      if (track === -1) track = ends.length;
      ends[track] = start + row.duration_minutes;
      tracks.set(row.id, track);
    }
    const count = Math.max(1, ends.length);
    for (const row of rows) {
      const height = (LANE_HEIGHT - 4) / count;
      out.set(row.id, { top: 2 + (tracks.get(row.id) ?? 0) * height, height });
    }
  }
  return out;
});

function horizontal(startMinute: number, minutes: number): { left: number; width: number } | null {
  const from = Math.max(startMinute, windowStart.value);
  const to = Math.min(startMinute + minutes, windowEnd.value);
  if (to <= from) return null;
  return { left: (from - windowStart.value) * PX_PER_MINUTE, width: (to - from) * PX_PER_MINUTE };
}

function blockStyle(row: AppointmentRow): Record<string, string> {
  const span = horizontal(minutesOf(row.start), row.duration_minutes) ?? { left: 0, width: 0 };
  const place = placed.value.get(row.id) ?? { top: 2, height: LANE_HEIGHT - 4 };
  const style: Record<string, string> = {
    left: `${span.left}px`,
    width: `${span.width}px`,
    top: `${place.top}px`,
    height: `${place.height}px`,
  };
  if (drag.value?.row.id === row.id && drag.value.active) {
    style.transform = `translate(${drag.value.dx}px, ${drag.value.dy}px)`;
    style.zIndex = '5';
  }
  return style;
}

const visibleRows = (lane: Lane) =>
  props.appointments.filter((row) => laneKeyOf(row) === lane.key && horizontal(minutesOf(row.start), row.duration_minutes));

function laneBlocks(lane: Lane): Array<{ block: BlockedTimeOut; left: number; width: number }> {
  const out = [];
  for (const block of props.blocks) {
    if (block.staff_id !== null && block.staff_id !== lane.staffId) continue;
    const startMinute = block.start.slice(0, 10) < props.day ? 0 : minutesOf(block.start);
    const endMinute = block.end.slice(0, 10) > props.day ? 24 * 60 : minutesOf(block.end);
    const span = horizontal(startMinute, endMinute - startMinute);
    if (span) out.push({ block, ...span });
  }
  return out;
}

function tapSlot(lane: Lane, minute: number): void {
  const bookable = lane.takesBookings && lane.staffId !== null;
  emit('slot', { staffId: bookable ? lane.staffId : null, staffName: bookable ? lane.name : '', time: hhmm(minute) });
}

const movable = (row: AppointmentRow): boolean => props.canMove && allows('edit', row, props.now);

// ── Dragging ──────────────────────────────────────────────────────────────────────────────────

interface Drag {
  row: AppointmentRow;
  laneIndex: number;
  startX: number;
  startY: number;
  dx: number;
  dy: number;
  active: boolean;
  touch: boolean;
  held: boolean;
  timer: ReturnType<typeof setTimeout> | null;
}

const drag = ref<Drag | null>(null);
/** A drag just ended: the click that follows it is not a tap. */
let swallowClick = false;

function snap(minutes: number): number {
  const step = Math.max(5, props.slotInterval);
  return Math.round(minutes / step) * step;
}

function onPointerDown(event: PointerEvent, row: AppointmentRow): void {
  if (!movable(row)) return;
  const touch = event.pointerType === 'touch';
  const laneIndex = lanes.value.findIndex((lane) => lane.key === laneKeyOf(row));
  const state: Drag = {
    row,
    laneIndex,
    startX: event.clientX,
    startY: event.clientY,
    dx: 0,
    dy: 0,
    active: false,
    touch,
    held: !touch,
    timer: null,
  };
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
  const rawX = event.clientX - state.startX;
  const rawY = event.clientY - state.startY;
  if (!state.held) {
    // A finger that moves before the hold completes is scrolling: the gesture is dropped.
    if (Math.hypot(rawX, rawY) > TOUCH_TOLERANCE) cancelDrag();
    return;
  }
  if (!state.active && Math.hypot(rawX, rawY) < DRAG_THRESHOLD) return;
  state.active = true;
  const minutes = snap(rawX / PX_PER_MINUTE);
  const lanesMoved = Math.round(rawY / LANE_HEIGHT);
  drag.value = { ...state, dx: minutes * PX_PER_MINUTE, dy: lanesMoved * LANE_HEIGHT };
}

function cancelDrag(): void {
  if (drag.value?.timer) clearTimeout(drag.value.timer);
  drag.value = null;
}

function onPointerUp(): void {
  const state = drag.value;
  cancelDrag();
  if (!state?.active) return;
  swallowClick = true;
  const minute = minutesOf(state.row.start) + Math.round(state.dx / PX_PER_MINUTE);
  const target = lanes.value[Math.min(lanes.value.length - 1, Math.max(0, state.laneIndex + Math.round(state.dy / LANE_HEIGHT)))];
  if (!target) return;
  const startsAt = new Date(`${props.day}T${hhmm(Math.max(0, minute))}:00${state.row.start.slice(19)}`);
  const inWindow = minute >= windowStart.value && minute + state.row.duration_minutes <= windowEnd.value;
  if (!inWindow || startsAt.getTime() < props.now.getTime()) return;
  const sameLane = target.key === laneKeyOf(state.row);
  if (sameLane && minute === minutesOf(state.row.start)) return;
  emit('move', { row: state.row, staffId: target.staffId, time: hhmm(minute) });
}

function onBlockClick(row: AppointmentRow): void {
  if (swallowClick) {
    swallowClick = false;
    return;
  }
  emit('open', row);
}

const label = (row: AppointmentRow): string =>
  `${formatTime(row.start.slice(11, 16), locale.value)} ${customerLabel(row, t)} — ${row.service_names}`;
</script>

<template>
  <div
    class="day-grid"
    data-testid="appointment-grid"
  >
    <p
      v-if="keptMessage"
      class="day-grid__kept"
      data-testid="appointment-grid-kept"
    >
      {{ keptMessage }}
    </p>
    <div
      class="day-grid__scroller"
      role="grid"
      :aria-label="$t('appointment.grid.label', { date: day })"
    >
      <div
        class="day-grid__header"
        :style="{ width: `${width + 140}px` }"
      >
        <div class="day-grid__corner" />
        <div
          class="day-grid__hours"
          :style="{ width: `${width}px` }"
        >
          <span
            v-for="hour in hours"
            :key="hour"
            class="day-grid__hour"
            data-testid="appointment-grid-hour"
            :style="{ width: `${60 * PX_PER_MINUTE}px` }"
          >{{ formatTime(`${pad(hour)}:00`, locale) }}</span>
        </div>
      </div>
      <div
        v-for="lane in lanes"
        :key="lane.key"
        class="day-grid__lane"
        :class="{ 'day-grid__lane--kept': !lane.takesBookings }"
        data-testid="appointment-grid-lane"
        :data-lane="lane.key"
        role="row"
        :style="{ width: `${width + 140}px`, height: `${LANE_HEIGHT}px` }"
      >
        <div
          class="day-grid__name"
          role="rowheader"
          :title="lane.name"
        >
          <span
            class="day-grid__swatch"
            :style="{ background: lane.color || 'var(--ion-color-medium, #9ca3af)' }"
          />
          <span class="day-grid__name-text">{{ lane.name }}</span>
        </div>
        <div
          class="day-grid__track"
          :style="{ width: `${width}px` }"
        >
          <template v-if="canBook">
            <button
              v-for="minute in slots"
              :key="minute"
              type="button"
              class="day-grid__slot"
              data-testid="appointment-grid-slot"
              :data-lane="lane.key"
              :data-time="hhmm(minute)"
              :style="{ left: `${(minute - windowStart) * PX_PER_MINUTE}px`, width: `${Math.max(5, slotInterval) * PX_PER_MINUTE}px` }"
              :aria-label="t('appointment.grid.slot', { staff: lane.name, time: formatTime(hhmm(minute), locale) })"
              @click="tapSlot(lane, minute)"
            />
          </template>
          <div
            v-for="painted in closedSpans"
            :key="`closed-${painted.key}`"
            class="day-grid__closed"
            data-testid="appointment-grid-closed"
            :style="{ left: `${painted.left}px`, width: `${painted.width}px` }"
          />
          <div
            v-for="painted in laneBlocks(lane)"
            :key="painted.block.id"
            class="day-grid__blocked"
            data-testid="appointment-grid-block"
            :title="painted.block.title"
            :style="{ left: `${painted.left}px`, width: `${painted.width}px` }"
          >
            {{ painted.block.title }}
          </div>
          <button
            v-for="row in visibleRows(lane)"
            :key="row.id"
            type="button"
            class="day-grid__appointment"
            :class="[`day-grid__appointment--${row.status}`, { 'day-grid__appointment--movable': movable(row) }]"
            data-testid="appointment-grid-appointment"
            :data-id="row.id"
            :aria-label="label(row)"
            :style="blockStyle(row)"
            @pointerdown="onPointerDown($event, row)"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="cancelDrag"
            @click="onBlockClick(row)"
          >
            <strong>{{ customerLabel(row, t) }}</strong>
            <span>{{ row.service_names }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.day-grid__kept {
  margin: 0 0 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--ion-color-warning, #ffc409) 18%, transparent);
  font-size: 0.88rem;
}
.day-grid__scroller {
  overflow-x: auto;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 10px;
}
.day-grid__header,
.day-grid__lane {
  display: flex;
}
.day-grid__header {
  position: sticky;
  top: 0;
  z-index: 3;
  background: var(--ion-background-color, #fff);
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}
.day-grid__corner,
.day-grid__name {
  position: sticky;
  left: 0;
  z-index: 2;
  flex: 0 0 140px;
  background: var(--ion-background-color, #fff);
}
.day-grid__name {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  font-size: 0.88rem;
  line-height: 1.2;
  border-right: 1px solid var(--ion-border-color, #e7e2d6);
  overflow: hidden;
}
/* A long name takes a second line before it ends in «…» (outfitkit#284); the whole one is its title. */
.day-grid__name-text {
  display: -webkit-box;
  min-width: 0;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
}
.day-grid__swatch {
  flex: 0 0 10px;
  height: 10px;
  border-radius: 50%;
}
.day-grid__hours {
  display: flex;
}
.day-grid__hour {
  flex: 0 0 auto;
  padding: 6px 4px;
  font-size: 0.78rem;
  color: var(--ion-color-medium, #6b7280);
  border-left: 1px solid var(--ion-border-color, #e7e2d6);
}
.day-grid__lane {
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}
.day-grid__lane--kept .day-grid__name {
  color: var(--ion-color-medium, #6b7280);
  font-style: italic;
}
.day-grid__track {
  position: relative;
  flex: 0 0 auto;
  background-image: linear-gradient(to right, var(--ion-border-color, #e7e2d6) 1px, transparent 1px);
  background-size: 96px 100%;
}
.day-grid__slot {
  position: absolute;
  top: 0;
  bottom: 0;
  border: 0;
  padding: 0;
  background: transparent;
  cursor: pointer;
}
.day-grid__slot:hover,
.day-grid__slot:focus-visible {
  background: color-mix(in srgb, var(--ion-color-primary, #3880ff) 10%, transparent);
  outline: none;
}
.day-grid__closed {
  position: absolute;
  top: 0;
  bottom: 0;
  pointer-events: none;
  background: color-mix(in srgb, var(--ion-color-medium, #9ca3af) 14%, transparent);
}
.day-grid__blocked {
  position: absolute;
  top: 0;
  bottom: 0;
  pointer-events: none;
  overflow: hidden;
  padding: 2px 4px;
  font-size: 0.72rem;
  color: var(--ion-color-medium, #6b7280);
  background: repeating-linear-gradient(
    45deg,
    color-mix(in srgb, var(--ion-color-medium, #9ca3af) 18%, transparent) 0 6px,
    transparent 6px 12px
  );
}
.day-grid__appointment {
  position: absolute;
  display: flex;
  flex-direction: column;
  justify-content: center;
  overflow: hidden;
  padding: 2px 6px;
  border: 0;
  border-left: 4px solid var(--ion-color-primary, #3880ff);
  border-radius: 6px;
  text-align: left;
  font-size: 0.78rem;
  line-height: 1.2;
  color: var(--ion-text-color, #1c1b17);
  background: color-mix(in srgb, var(--ion-color-primary, #3880ff) 16%, var(--ion-background-color, #fff));
  white-space: nowrap;
  cursor: pointer;
  touch-action: pan-x pan-y;
}
.day-grid__appointment--movable {
  cursor: grab;
}
.day-grid__appointment--pending {
  border-left-color: var(--ion-color-warning, #ffc409);
}
.day-grid__appointment--in_progress {
  border-left-color: var(--ion-color-tertiary, #5260ff);
}
.day-grid__appointment--completed {
  border-left-color: var(--ion-color-success, #2dd36f);
}
.day-grid__appointment--cancelled,
.day-grid__appointment--no_show {
  opacity: 0.55;
  border-left-color: var(--ion-color-medium, #9ca3af);
  text-decoration: line-through;
}
</style>
