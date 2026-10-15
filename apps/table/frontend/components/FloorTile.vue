<script setup lang="ts">
// A table on the floor plan (WORKBOOK «Plano de sala»; TABLE-F09), at its own box of the plan: its
// number; its seats («4 pax») or, occupied, the guests and the minutes they have been there («3 pax ·
// 35 min») and who serves them; a reservation of today on one line (the name cut with «…», the hour
// never); and its status written with its icon and colour — never the colour alone (tables#64). The
// canvas around it owns the pointer and the keys; this only paints. While a transfer or a merge picks
// its destination, a table that cannot be picked is dimmed and disabled.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { clock, minutesSince } from '../lib/format';
import { holdName, STATUS_COLOR, STATUS_ICON } from '../lib/floor';
import type { TableOut } from '../operations';

const props = withDefaults(
  defineProps<{
    table: TableOut;
    now: Date;
    /** The business's time zone (IANA): the hour of a reservation. */
    timeZone: string;
    /** «Edit plan»: an inactive table is shown, greyed out. */
    editing?: boolean;
    /** Picking a destination: `true` = may be picked, `false` = dimmed; `undefined` = not picking. */
    pickable?: boolean;
    /** It is being dragged. */
    dragging?: boolean;
    /** Where it is painted while dragged (before the server has it). */
    x?: number;
    y?: number;
  }>(),
  { editing: false, pickable: undefined, dragging: false, x: undefined, y: undefined },
);

const t = useT();
const locale = useLocale();

const statusLabel = computed(() => t(`table.status.${props.table.status}`));
const minutes = computed(() => minutesSince(props.table.since, props.now));
const live = computed(() => {
  if (props.table.status !== 'occupied' || !props.table.guests) return '';
  const parts = [t('table.pax', { count: props.table.guests })];
  if (minutes.value !== null) parts.push(t('table.minutes', { minutes: minutes.value }));
  return parts.join(' · ');
});
const line = computed(() => live.value || t('table.pax', { count: props.table.capacity }));
const waiter = computed(() => (props.table.status === 'occupied' ? props.table.waiter_name : ''));
const holder = computed(() => holdName(props.table.hold, t('table.erasedCustomer')));
const holdTime = computed(() => clock(props.table.hold?.held_from, locale.value, props.timeZone));
const holdSpan = computed(() =>
  [holdTime.value, clock(props.table.hold?.held_until, locale.value, props.timeZone)].filter(Boolean).join('–'),
);

const accessibleName = computed(() =>
  [
    t('table.tableLabel', { number: props.table.number }),
    props.table.zone_name ?? '',
    t('table.pax', { count: props.table.capacity }),
    statusLabel.value,
    props.table.status === 'occupied' && props.table.guests ? t('table.guestsCount', { count: props.table.guests }) : '',
    props.table.status === 'occupied' && minutes.value !== null ? t('table.minutes', { minutes: minutes.value }) : '',
    waiter.value ? t('table.servedBy', { name: waiter.value }) : '',
    holder.value ? t('table.reservedFor', { name: holder.value }) : '',
  ]
    .filter(Boolean)
    .join(' · '),
);

const tooltip = computed(() =>
  [
    t('table.floor.tileTitle', { status: statusLabel.value, count: props.table.capacity }),
    live.value,
    waiter.value ? t('table.servedBy', { name: waiter.value }) : '',
    holder.value ? `${t('table.reservedFor', { name: holder.value })} ${holdSpan.value}`.trim() : '',
  ]
    .filter(Boolean)
    .join(' · '),
);

const inactive = computed(() => props.editing && !props.table.in_service);
const classes = computed(() => ({
  'table-tile': true,
  'table-tile--round': props.table.shape === 'round',
  'table-tile--inactive': inactive.value,
  'table-tile--dragging': props.dragging,
  'table-tile--dimmed': props.pickable === false,
  'table-tile--target': props.pickable === true,
}));
const style = computed(() => ({
  left: `${props.x ?? props.table.position_x}px`,
  top: `${props.y ?? props.table.position_y}px`,
  width: `${props.table.width}px`,
  height: `${props.table.height}px`,
  borderColor: STATUS_COLOR[props.table.status],
}));
</script>

<template>
  <div
    :class="classes"
    :style="style"
    role="button"
    :tabindex="pickable === false ? -1 : 0"
    :aria-label="accessibleName"
    :aria-disabled="pickable === false ? 'true' : undefined"
    :title="tooltip"
    :data-status="table.status"
    :data-testid="`table-floor-tile-${table.id}`"
  >
    <div
      class="table-tile__number"
      data-part="number"
    >
      {{ table.number }}
    </div>
    <div
      class="table-tile__line"
      data-part="line"
    >
      {{ line }}
    </div>
    <div
      v-if="waiter"
      class="table-tile__waiter"
      data-part="waiter"
    >
      {{ waiter }}
    </div>
    <div
      v-if="holder"
      class="table-tile__hold"
    >
      <span
        class="table-tile__hold-name"
        data-part="hold-name"
      >{{ holder }}</span>
      <span
        v-if="holdTime"
        class="table-tile__hold-time"
        data-part="hold-time"
      >· {{ holdTime }}</span>
    </div>
    <div
      v-if="inactive"
      class="table-tile__inactive"
      data-part="inactive"
    >
      {{ $t('table.inactive') }}
    </div>
    <div
      class="table-tile__status"
      data-part="status"
      :style="{ color: STATUS_COLOR[table.status] }"
    >
      <HubIcon :name="STATUS_ICON[table.status]" />{{ statusLabel }}
    </div>
  </div>
</template>

<style scoped>
.table-tile {
  position: absolute;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.1rem 0.15rem;
  overflow: hidden;
  border: 2px solid;
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-background-color, #fff);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.12);
  color: var(--ion-text-color, #1c1b18);
  line-height: 1.12;
  text-align: center;
  user-select: none;
  touch-action: none;
  cursor: pointer;
}
.table-tile > * {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.table-tile--round {
  border-radius: 50%;
}
.table-tile--dragging {
  cursor: grabbing;
  opacity: 0.85;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.28);
  z-index: 5;
}
.table-tile--inactive {
  opacity: 0.5;
  border-style: dashed;
}
.table-tile--dimmed {
  opacity: 0.35;
  cursor: not-allowed;
}
.table-tile--target {
  outline: 2px dashed var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}
.table-tile:focus-visible {
  outline: 3px solid var(--ion-color-primary, #0091ce);
  outline-offset: 2px;
}
.table-tile__number {
  font-size: 1rem;
  font-weight: 700;
}
.table-tile__line,
.table-tile__waiter,
.table-tile__inactive {
  font-size: 0.56rem;
}
.table-tile__line {
  color: var(--ion-color-medium, #8b897f);
}
.table-tile__waiter {
  font-weight: 600;
}
.table-tile__hold {
  display: flex;
  justify-content: center;
  gap: 0.2em;
  min-width: 0;
  font-size: 0.62rem;
  font-weight: 600;
  color: var(--ion-color-warning, #f08c00);
}
.table-tile__hold-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.table-tile__hold-time {
  flex: none;
}
.table-tile__status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.12rem;
  font-size: 0.55rem;
  font-weight: 700;
}
.table-tile__status ion-icon {
  flex: none;
  font-size: 0.7rem;
}
</style>
