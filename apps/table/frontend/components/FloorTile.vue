<script setup lang="ts">
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { paintBox, type FloorFit } from '../lib/floor-fit';
import { STATUS_ICON } from '../lib/floor';
import { floorView } from '../lib/floor-view';
import type { SettingsOut, TableOut } from '../operations';
import TableGlyph from './TableGlyph.vue';

const props = withDefaults(
  defineProps<{
    table: TableOut;
    now: Date;
    timeZone: string;
    settings: SettingsOut;
    fit?: FloorFit;
    editing?: boolean;
    pickable?: boolean;
    dragging?: boolean;
    x?: number;
    y?: number;
  }>(),
  { fit: () => ({ spread: 1, box: 1, plane: { w: 0, h: 0 } }), editing: false, pickable: undefined, dragging: false, x: undefined, y: undefined },
);

const t = useT();
const locale = useLocale();
const model = computed(() => floorView(props.table, { now: props.now, settings: props.settings, locale: locale.value, timeZone: props.timeZone, t }));
const inactive = computed(() => props.editing && !props.table.in_service);
const classes = computed(() => ({
  'table-tile': true,
  'table-tile--round': props.table.shape === 'round',
  'table-tile--rectangle': props.table.shape === 'rectangle',
  'table-tile--inactive': inactive.value,
  'table-tile--dragging': props.dragging,
  'table-tile--dimmed': props.pickable === false,
  'table-tile--target': props.pickable === true,
}));
const style = computed(() => {
  const table = { ...props.table, position_x: props.x ?? props.table.position_x, position_y: props.y ?? props.table.position_y };
  const box = paintBox(table, props.fit);
  return { left: `${box.x}px`, top: `${box.y}px`, width: `${box.width}px`, height: `${box.height}px` };
});
</script>

<template>
  <div
    :class="classes"
    :style="style"
    :data-status="table.status"
    :data-timer="model.tone"
    :data-x="x ?? table.position_x"
    :data-y="y ?? table.position_y"
    :data-testid="`table-floor-tile-${table.id}`"
  >
    <TableGlyph
      :table="table"
      :tone="model.tone"
      :progress="model.progress"
    />
    <button
      class="table-tile__button"
      type="button"
      :aria-label="model.accessible"
      :aria-disabled="pickable === false ? 'true' : undefined"
      :tabindex="pickable === false ? -1 : 0"
      :disabled="pickable === false"
      :title="model.accessible"
    >
      <span
        class="table-tile__number"
        data-part="number"
      >{{ table.number }}</span>
      <span
        class="table-tile__line"
        :data-tone="model.tone"
        data-part="line"
      >{{ model.short }}</span>
    </button>
    <div class="table-tile__caption">
      <span
        class="table-tile__status"
        data-part="status"
      >
        <HubIcon :name="STATUS_ICON[table.status]" />
        {{ model.labels[0] }}
      </span>
      <span
        v-if="model.holder"
        class="table-tile__hold"
      >
        <span
          class="table-tile__hold-name"
          data-part="hold-name"
        >{{ model.holder }}</span>
        <span
          v-if="model.holdTime"
          class="table-tile__hold-time"
          data-part="hold-time"
        >· {{ model.holdTime }}</span>
      </span>
      <span
        v-if="inactive"
        class="table-tile__inactive"
        data-part="inactive"
      >{{ $t('table.inactive') }}</span>
    </div>
  </div>
</template>

<style scoped src="./floor-status.css"></style>

<style scoped>
.table-tile {
  --tile-shadow: 0 8px 24px color-mix(in srgb, var(--ion-text-color) 11%, transparent);
  position: absolute;
  container-type: inline-size;
  user-select: none;
}
.table-tile[data-status='occupied'] {
  --tile-shadow: 0 12px 30px color-mix(in srgb, var(--table-bg) 30%, transparent);
}
.table-tile__button {
  position: relative;
  z-index: 2;
  display: flex;
  width: 100%;
  height: 100%;
  min-width: var(--ep-touch-min);
  min-height: var(--ep-touch-min);
  box-sizing: border-box;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 5cqi;
  padding: 8cqi;
  border: 1px solid var(--table-edge);
  border-radius: var(--ep-radius-lg);
  background: var(--table-bg);
  box-shadow: var(--tile-shadow);
  color: var(--table-ink);
  font: inherit;
  cursor: pointer;
  transition: background-color 420ms, color 420ms, border-color 420ms, opacity 250ms, scale 180ms;
  touch-action: manipulation;
}
.table-tile--round .table-tile__button {
  border-radius: 50%;
}
.table-tile[data-status='reserved'] .table-tile__button {
  border-width: 2px;
  border-style: dashed;
}
.table-tile[data-status='blocked'] .table-tile__button {
  background: repeating-linear-gradient(135deg, var(--ion-card-background), var(--ion-card-background) 8px, color-mix(in srgb, var(--ion-color-medium) 12%, var(--ion-card-background)) 8px, color-mix(in srgb, var(--ion-color-medium) 12%, var(--ion-card-background)) 12px);
}
.table-tile__button:hover {
  scale: 1.025;
}
.table-tile__button:focus-visible {
  outline: 2px solid var(--ep-primary-text);
  outline-offset: 3px;
  box-shadow: var(--ep-focus-ring);
}
.table-tile__number {
  font-size: 32cqi;
  font-weight: 750;
  line-height: 1;
  letter-spacing: -0.045em;
}
.table-tile__line {
  max-width: 100%;
  padding: 0.2em 0.45em;
  border-radius: 0.6em;
  font-size: 12cqi;
  font-weight: 750;
  line-height: 1.2;
  white-space: nowrap;
}
.table-tile[data-status='occupied'] .table-tile__line[data-tone='warning'] {
  background: var(--ep-warning-tint);
  color: var(--ep-warning-text);
}
.table-tile[data-status='occupied'] .table-tile__line[data-tone='critical'] {
  background: var(--ep-danger-tint);
  color: var(--ep-danger-text);
}
.table-tile__caption {
  position: absolute;
  top: calc(100% + 17cqi);
  left: 50%;
  display: flex;
  width: max-content;
  max-width: 200cqi;
  flex-direction: column;
  gap: 3px;
  font-size: 12cqi;
  font-weight: 600;
  line-height: 1.25;
  text-align: center;
  transform: translateX(-50%);
  pointer-events: none;
}
.table-tile__status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.25em;
  white-space: nowrap;
}
.table-tile__hold {
  color: var(--ep-warning-text);
  overflow-wrap: anywhere;
}
.table-tile__hold-time {
  margin-inline-start: 0.3em;
  white-space: nowrap;
}
.table-tile--inactive,
.table-tile--dimmed {
  opacity: 0.4;
}
.table-tile--dimmed .table-tile__button {
  cursor: not-allowed;
}
.table-tile--target .table-tile__button {
  outline: 2px solid var(--ep-primary-text);
  outline-offset: 5px;
  animation: table-target 1.8s ease-in-out infinite;
}
.table-tile--dragging {
  z-index: 10;
}
.table-tile--dragging .table-tile__button {
  cursor: grabbing;
  scale: 1.04;
}
@keyframes table-target {
  50% {
    box-shadow: 0 0 0 8px transparent;
  }
}
@media (prefers-reduced-motion: reduce) {
  .table-tile__button,
  .table-tile--target .table-tile__button {
    animation: none;
    transition: none;
  }
  .table-tile__button:hover,
  .table-tile--dragging .table-tile__button {
    scale: 1;
  }
}
</style>
