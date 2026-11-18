<script setup lang="ts">
// The plan of a zone: the positions spread to fit the stage (never below a legible size; past that the
// stage scrolls on both axes, with a fade on every edge that has tables behind it, a mouse drags its
// background and the focused stage scrolls with the arrows). In «Service» a tap or the keyboard picks a
// table (`select`); in «Edit plan» a press that travels drags it (the screen distance over the spread), one
// that does not is a tap, and the arrows move a focused table. A table never leaves the plan; its new place
// shows at once (`move`) until the server's row has it, and `revert(id)` puts a refused one back.
import { FloorTile, useScrollEdges } from '@erplora/ui/components';
import { computed, ref, shallowRef, useTemplateRef, watch } from 'vue';

import { useFloorFit } from '../composables/useFloorFit';
import { useFloorViews } from '../composables/useFloorViews';
import { useStagePan } from '../composables/useStagePan';
import { useT } from '../composables/useT';
import { clampPosition, DRAG_THRESHOLD, keyDelta, planeSize, type Size } from '../lib/floor';
import { paintBox } from '../lib/floor-fit';
import type { SettingsOut, TableOut } from '../operations';

const props = withDefaults(
  defineProps<{
    tables: TableOut[];
    now: Date;
    timeZone: string;
    settings: SettingsOut;
    editable?: boolean;
    /** Picking the destination of a transfer or a merge: which tables may be picked. */
    pick?: ((table: TableOut) => boolean) | null;
  }>(),
  { editable: false, pick: null },
);

const emit = defineEmits<{
  select: [table: TableOut];
  move: [move: { table: TableOut; x: number; y: number }];
}>();

interface Drag {
  id: string;
  startX: number;
  startY: number;
  fromX: number;
  fromY: number;
  moved: boolean;
}

const EDGES = ['left', 'right', 'top', 'bottom'] as const;

/** Places shown before the server has them, by table id. */
const local = ref<Record<string, { x: number; y: number }>>({});
const drag = shallowRef<Drag | null>(null);
/** The plan's size when a drag started: neither the plan nor its scale changes under the finger. */
const floor = shallowRef<Size | undefined>();
const stage = useTemplateRef<HTMLElement>('stage');
const plane = useTemplateRef<HTMLElement>('plane');

const shown = computed(() =>
  props.tables.map((table) => {
    const place = local.value[table.id];
    return place ? { ...table, position_x: place.x, position_y: place.y } : table;
  }),
);
const size = computed(() => planeSize(shown.value, floor.value));
const { fit } = useFloorFit(
  stage,
  computed(() => floor.value ?? size.value),
);
const painted = computed(() => ({ w: rounded(size.value.w * fit.value.spread), h: rounded(size.value.h * fit.value.spread) }));
const t = useT();
const views = useFloorViews(
  () => shown.value,
  () => ({ now: props.now, settings: props.settings, timeZone: props.timeZone, pick: props.pick }),
);
const tiles = computed(() =>
  shown.value.map((table, index) => ({
    table,
    view: views.value[index],
    box: paintBox(table, fit.value),
    inactive: props.editable && !table.in_service ? t('table.inactive') : '',
  })),
);
const { panning, onPointerDown: panDown, onPointerMove: panMove, onPointerUp: panUp, onKeydown: panKey } = useStagePan(stage);

function rounded(value: number): number {
  return Math.round(value * 1000) / 1000;
}

// The server's row has the place now: the local one is no longer needed.
watch(
  () => props.tables,
  (tables) => {
    const next = { ...local.value };
    for (const table of tables) {
      const place = next[table.id];
      if (place && place.x === table.position_x && place.y === table.position_y) delete next[table.id];
    }
    local.value = next;
  },
);

function revert(id: string): void {
  const next = { ...local.value };
  delete next[id];
  local.value = next;
}
defineExpose({ revert });

/** The plan's size in plan units, to keep a table inside: what is painted, never less than the tables need. */
function bounds(): Size {
  const spread = fit.value.spread;
  const box = plane.value;
  return { w: Math.max((box?.clientWidth ?? 0) / spread, size.value.w), h: Math.max((box?.clientHeight ?? 0) / spread, size.value.h) };
}

function place(table: TableOut, x: number, y: number): { x: number; y: number } {
  const spot = clampPosition(x, y, { w: table.width, h: table.height }, bounds());
  local.value = { ...local.value, [table.id]: spot };
  return spot;
}

function onClick(table: TableOut, event: MouseEvent): void {
  if (props.pick && !props.pick(table)) return;
  // In «Edit plan» a pointer's tap was answered on its release; a click with no pointer is Enter or Space.
  if (props.editable && event.detail !== 0) return;
  emit('select', table);
}

function onTileDown(table: TableOut, event: PointerEvent): void {
  if (!props.editable) return;
  const current = shown.value.find((row) => row.id === table.id) ?? table;
  floor.value = size.value;
  drag.value = { id: table.id, startX: event.clientX, startY: event.clientY, fromX: current.position_x, fromY: current.position_y, moved: false };
  (event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function onPointerMove(event: PointerEvent): void {
  panMove(event);
  const current = drag.value;
  if (!current) return;
  const dx = event.clientX - current.startX;
  const dy = event.clientY - current.startY;
  if (!current.moved && Math.abs(dx) <= DRAG_THRESHOLD && Math.abs(dy) <= DRAG_THRESHOLD) return;
  drag.value = { ...current, moved: true };
  const table = props.tables.find((row) => row.id === current.id);
  const spread = fit.value.spread;
  if (table) place(table, current.fromX + dx / spread, current.fromY + dy / spread);
}

function onPointerUp(): void {
  panUp();
  const current = drag.value;
  drag.value = null;
  floor.value = undefined;
  if (!current) return;
  const table = props.tables.find((row) => row.id === current.id);
  if (!table) return;
  if (!current.moved) {
    emit('select', table);
    return;
  }
  const spot = local.value[table.id];
  if (spot) emit('move', { table, x: spot.x, y: spot.y });
}

function onKeydown(table: TableOut, event: KeyboardEvent): void {
  if (!props.editable) return;
  const delta = keyDelta(event.key, event.shiftKey);
  if (!delta) return;
  event.preventDefault();
  const current = shown.value.find((row) => row.id === table.id) ?? table;
  const spot = place(table, current.position_x + delta[0], current.position_y + delta[1]);
  emit('move', { table, x: spot.x, y: spot.y });
}

// Each edge of the stage with tables behind it fades out (a hard cut reads «no more tables»).
const { edges, mark: markEdges } = useScrollEdges(stage, () => [plane.value]);
watch(painted, () => queueMicrotask(markEdges));
const edgeClasses = computed(() => Object.fromEntries(EDGES.map((edge) => [`table-canvas--more-${edge}`, edges.value[edge]])));
</script>

<template>
  <div
    class="table-canvas"
    :class="edgeClasses"
    data-testid="table-floor-canvas"
  >
    <div
      ref="stage"
      class="table-canvas__stage"
      :class="{ 'table-canvas__stage--panning': panning }"
      data-testid="table-floor-stage"
      role="region"
      tabindex="0"
      :aria-label="$t('table.floor.planLabel')"
      @pointerdown="panDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @pointercancel="onPointerUp"
      @keydown="panKey"
    >
      <div
        ref="plane"
        class="table-canvas__plane"
        :class="{ 'table-canvas__plane--grid': editable }"
        data-testid="table-floor-plane"
        :style="{ width: `${painted.w}px`, height: `${painted.h}px` }"
      >
        <FloorTile
          v-for="tile in tiles"
          :key="tile.table.id"
          :table="tile.view"
          :box="tile.box"
          :inactive-label="tile.inactive"
          :editing="editable"
          :dragging="drag?.id === tile.table.id && drag.moved"
          :data-x="tile.table.position_x"
          :data-y="tile.table.position_y"
          @click="onClick(tile.table, $event)"
          @pointerdown="onTileDown(tile.table, $event)"
          @keydown="onKeydown(tile.table, $event)"
        />
      </div>
    </div>
    <span
      v-for="edge in EDGES"
      :key="edge"
      class="table-canvas__fade"
      :class="`table-canvas__fade--${edge}`"
      aria-hidden="true"
    />
    <slot />
  </div>
</template>

<style scoped>
.table-canvas {
  --canvas-zone: var(--zone-color, var(--ion-color-primary));
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
}
.table-canvas__stage {
  position: relative;
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: auto;
  padding: 16px;
  border-radius: 20px;
  background:
    radial-gradient(circle at 50% 40%, color-mix(in srgb, var(--canvas-zone) 7%, transparent), transparent 68%),
    color-mix(in srgb, var(--canvas-zone) 2%, var(--ion-card-background));
  touch-action: pan-x pan-y;
}
.table-canvas__stage:focus-visible {
  outline: 2px solid var(--ep-primary-text);
  outline-offset: 3px;
  box-shadow: var(--ep-focus-ring);
}
.table-canvas__stage--panning {
  cursor: grabbing;
  user-select: none;
}
.table-canvas__plane {
  position: relative;
  flex: none;
  margin: auto;
}
.table-canvas__plane--grid {
  --canvas-grid: color-mix(in srgb, var(--ion-color-primary) 12%, transparent);
  min-width: 100%;
  min-height: 100%;
  margin: 0;
  background-image: linear-gradient(var(--canvas-grid) 1px, transparent 1px), linear-gradient(90deg, var(--canvas-grid) 1px, transparent 1px);
  background-position: 20px 20px;
  background-size: 40px 40px;
}
.table-canvas__fade {
  position: absolute;
  z-index: 3;
  opacity: 0;
  pointer-events: none;
  transition: opacity 160ms;
}
.table-canvas__fade--left,
.table-canvas__fade--right {
  top: 0;
  bottom: 0;
  width: 30px;
}
.table-canvas__fade--top,
.table-canvas__fade--bottom {
  right: 0;
  left: 0;
  height: 26px;
}
.table-canvas__fade--left {
  left: 0;
  background: linear-gradient(to right, var(--ion-card-background), transparent);
}
.table-canvas__fade--right {
  right: 0;
  background: linear-gradient(to left, var(--ion-card-background), transparent);
}
.table-canvas__fade--top {
  top: 0;
  background: linear-gradient(to bottom, var(--ion-card-background), transparent);
}
.table-canvas__fade--bottom {
  bottom: 0;
  background: linear-gradient(to top, var(--ion-card-background), transparent);
}
.table-canvas--more-left .table-canvas__fade--left,
.table-canvas--more-right .table-canvas__fade--right,
.table-canvas--more-top .table-canvas__fade--top,
.table-canvas--more-bottom .table-canvas__fade--bottom {
  opacity: 0.9;
}
@media (prefers-reduced-motion: reduce) {
  .table-canvas__fade {
    transition: none;
  }
}
</style>
