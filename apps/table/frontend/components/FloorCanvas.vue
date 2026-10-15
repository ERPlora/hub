<script setup lang="ts">
// The plan of a zone (WORKBOOK «Plano de sala»; TABLE-F03, F09): a window (`.table-canvas`) onto a plan
// as large as its farthest table (tables keep their real size: on a phone the window scrolls sideways
// and each edge with tables behind it fades out; it grows down with the page).
// - «Service» (`editable` false): a tap (click) or Enter picks a table (`select`); nothing moves.
// - «Edit plan»: the gesture is the table's (pointer events): a press that travels more than 5 px drags
//   it, one that does not is a tap; the arrows move a focused table 8 px (32 with Shift). It never
//   leaves the plan, and while one is dragged the plan does not shrink under the finger. The new place
//   shows at once (`move` tells the page) and stays until the server's row has it; `revert(id)` puts a
//   refused one back.
// - Picking the destination of a transfer or a merge (`pick`): only the tables it accepts answer.
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, useTemplateRef, watch } from 'vue';

import { clampPosition, DRAG_THRESHOLD, keyDelta, planeSize, type Size } from '../lib/floor';
import type { TableOut } from '../operations';
import FloorTile from './FloorTile.vue';

const props = withDefaults(
  defineProps<{
    tables: TableOut[];
    now: Date;
    timeZone: string;
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

/** Places shown before the server has them, by table id. */
const local = ref<Record<string, { x: number; y: number }>>({});
const drag = shallowRef<Drag | null>(null);
/** The plan's size when a drag started: it never shrinks below it while the table is dragged. */
const floor = shallowRef<Size | undefined>();
const win = useTemplateRef<HTMLElement>('win');
const plane = useTemplateRef<HTMLElement>('plane');

const shown = computed(() =>
  props.tables.map((table) => {
    const place = local.value[table.id];
    return place ? { ...table, position_x: place.x, position_y: place.y } : table;
  }),
);
const size = computed(() => planeSize(shown.value, floor.value));

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

function pickable(table: TableOut): boolean | undefined {
  return props.pick ? props.pick(table) : undefined;
}

/** The plan's size to keep a table inside: what is painted, never less than the tables need. */
function bounds(): Size {
  const painted = plane.value;
  return { w: Math.max(painted?.clientWidth ?? 0, size.value.w), h: Math.max(painted?.clientHeight ?? 0, size.value.h) };
}

function place(table: TableOut, x: number, y: number): { x: number; y: number } {
  const spot = clampPosition(x, y, { w: table.width, h: table.height }, bounds());
  local.value = { ...local.value, [table.id]: spot };
  return spot;
}

function onClick(table: TableOut): void {
  if (props.editable || pickable(table) === false) return;
  emit('select', table);
}

function onPointerDown(table: TableOut, event: PointerEvent): void {
  if (!props.editable) return;
  const current = shown.value.find((row) => row.id === table.id) ?? table;
  floor.value = size.value;
  drag.value = { id: table.id, startX: event.clientX, startY: event.clientY, fromX: current.position_x, fromY: current.position_y, moved: false };
  (event.currentTarget as HTMLElement | null)?.setPointerCapture?.(event.pointerId);
  event.preventDefault();
}

function onPointerMove(event: PointerEvent): void {
  const current = drag.value;
  if (!current) return;
  const dx = event.clientX - current.startX;
  const dy = event.clientY - current.startY;
  if (!current.moved && Math.abs(dx) <= DRAG_THRESHOLD && Math.abs(dy) <= DRAG_THRESHOLD) return;
  drag.value = { ...current, moved: true };
  const table = props.tables.find((row) => row.id === current.id);
  if (table) place(table, current.fromX + dx, current.fromY + dy);
}

function onPointerUp(): void {
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
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault();
    if (pickable(table) !== false) emit('select', table);
    return;
  }
  if (!props.editable) return;
  const delta = keyDelta(event.key, event.shiftKey);
  if (!delta) return;
  event.preventDefault();
  const current = shown.value.find((row) => row.id === table.id) ?? table;
  const spot = place(table, current.position_x + delta[0], current.position_y + delta[1]);
  emit('move', { table, x: spot.x, y: spot.y });
}

// Each edge of the window with tables behind it fades out (a hard cut reads «no more tables»).
const edges = ref({ left: false, right: false });
function markEdges(): void {
  const el = win.value;
  if (!el) return;
  const hidden = el.scrollWidth - el.clientWidth;
  edges.value = { left: el.scrollLeft > 1, right: el.scrollLeft < hidden - 1 };
}
let observer: ResizeObserver | null = null;
onMounted(() => {
  markEdges();
  if (typeof ResizeObserver !== 'undefined' && win.value) {
    observer = new ResizeObserver(markEdges);
    observer.observe(win.value);
    if (plane.value) observer.observe(plane.value);
  }
});
onBeforeUnmount(() => observer?.disconnect());
watch(size, () => queueMicrotask(markEdges));
</script>

<template>
  <div
    ref="win"
    class="table-canvas"
    :class="{ 'table-canvas--more-left': edges.left, 'table-canvas--more-right': edges.right }"
    data-testid="table-floor-canvas"
    @scroll="markEdges"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <div
      ref="plane"
      class="table-canvas__plane"
      data-testid="table-floor-plane"
      :style="{ width: `${size.w}px`, height: `${size.h}px` }"
    >
      <FloorTile
        v-for="table in shown"
        :key="table.id"
        :table="table"
        :now="now"
        :time-zone="timeZone"
        :editing="editable"
        :pickable="pickable(table)"
        :dragging="drag?.id === table.id && drag.moved"
        :class="{ 'table-tile--editable': editable }"
        @click="onClick(table)"
        @pointerdown="onPointerDown(table, $event)"
        @keydown="onKeydown(table, $event)"
      />
      <slot />
    </div>
  </div>
</template>

<style scoped>
.table-canvas {
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  border: 1px dashed var(--ion-border-color, #cfcabd);
  border-radius: var(--ep-radius, 14px);
  touch-action: pan-x pan-y;
}
.table-canvas__plane {
  position: relative;
  min-width: 100%;
  min-height: max(60vh, 22rem);
  background:
    repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(0, 0, 0, 0.04) 40px),
    repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(0, 0, 0, 0.04) 40px);
}
.table-canvas--more-right {
  -webkit-mask-image: linear-gradient(to right, #000 calc(100% - 2.5rem), transparent);
  mask-image: linear-gradient(to right, #000 calc(100% - 2.5rem), transparent);
}
.table-canvas--more-left {
  -webkit-mask-image: linear-gradient(to left, #000 calc(100% - 2.5rem), transparent);
  mask-image: linear-gradient(to left, #000 calc(100% - 2.5rem), transparent);
}
.table-canvas--more-left.table-canvas--more-right {
  -webkit-mask-image: linear-gradient(to right, transparent, #000 2.5rem, #000 calc(100% - 2.5rem), transparent);
  mask-image: linear-gradient(to right, transparent, #000 2.5rem, #000 calc(100% - 2.5rem), transparent);
}
:deep(.table-tile:not(.table-tile--editable)) {
  touch-action: manipulation;
}
:deep(.table-tile--editable) {
  cursor: grab;
}
</style>
