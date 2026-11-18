<script setup lang="ts">
import { computed } from 'vue';

import { paintedRatio } from '../lib/floor-fit';
import { filledSeats, seatSpots } from '../lib/floor-seats';
import type { TableOut } from '../operations';

const props = withDefaults(
  defineProps<{
    table: TableOut;
    tone: 'normal' | 'warning' | 'critical';
    progress: number;
    variant?: 'plan' | 'mini';
  }>(),
  { variant: 'plan' },
);

const spots = computed(() => seatSpots(props.table.capacity, props.table.shape, paintedRatio(props.table)));
const filled = computed(() => filledSeats(props.table.capacity, props.table.guests));
const dash = computed(() => `${Math.max(0, Math.min(100, props.progress))} ${Math.max(0, 100 - props.progress)}`);

function seatStyle(spot: { x: number; y: number; rotation: number }): Record<string, string> {
  return { left: `${spot.x}%`, top: `${spot.y}%`, '--seat-rotation': `${spot.rotation}deg` };
}
</script>

<template>
  <div
    class="table-glyph"
    :class="`table-glyph--${variant}`"
    :data-status="table.status"
    :data-shape="table.shape"
    :data-tone="tone"
    aria-hidden="true"
  >
    <span
      v-for="(spot, index) in spots"
      :key="index"
      class="table-glyph__seat"
      :class="{ 'table-glyph__seat--filled': index < filled }"
      :style="seatStyle(spot)"
      data-part="seat"
    />
    <span
      v-if="variant === 'mini'"
      class="table-glyph__body"
    />
    <svg
      v-if="table.status === 'occupied'"
      class="table-glyph__arc"
      :data-tone="tone"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      <template v-if="table.shape === 'round'">
        <circle
          class="table-glyph__arc-track"
          cx="50"
          cy="50"
          r="48"
          pathLength="100"
          vector-effect="non-scaling-stroke"
        />
        <circle
          v-if="progress > 0"
          class="table-glyph__arc-value"
          cx="50"
          cy="50"
          r="48"
          pathLength="100"
          vector-effect="non-scaling-stroke"
          :stroke-dasharray="dash"
        />
      </template>
      <template v-else>
        <rect
          class="table-glyph__arc-track"
          x="1"
          y="1"
          width="98"
          height="98"
          rx="14"
          pathLength="100"
          vector-effect="non-scaling-stroke"
        />
        <rect
          v-if="progress > 0"
          class="table-glyph__arc-value"
          x="1"
          y="1"
          width="98"
          height="98"
          rx="14"
          pathLength="100"
          vector-effect="non-scaling-stroke"
          :stroke-dasharray="dash"
        />
      </template>
    </svg>
  </div>
</template>

<style scoped src="./floor-status.css"></style>

<style scoped>
.table-glyph {
  --glyph-seat-empty: color-mix(in srgb, var(--ion-color-medium) 35%, var(--ion-card-background));
  --glyph-seat-filled: var(--ep-primary-text);
  --glyph-timer: var(--ep-primary-text);
  position: absolute;
  inset: 0;
  container-type: inline-size;
  pointer-events: none;
}
.table-glyph[data-tone='warning'] {
  --glyph-timer: var(--ep-warning-text);
}
.table-glyph[data-tone='critical'] {
  --glyph-timer: var(--ep-danger-text);
}
.table-glyph__seat {
  position: absolute;
  width: 18cqi;
  height: 10cqi;
  border: 1px solid color-mix(in srgb, var(--ion-color-medium) 32%, transparent);
  border-radius: 5cqi;
  background: var(--glyph-seat-empty);
  box-shadow: var(--ep-shadow-xs, none);
  transform: translate(-50%, -50%) rotate(var(--seat-rotation));
  transition: background-color 400ms, transform 300ms;
}
.table-glyph__seat--filled {
  border-color: transparent;
  background: var(--glyph-seat-filled);
}
.table-glyph__arc {
  position: absolute;
  top: -8cqi;
  left: -8cqi;
  width: calc(100% + 16cqi);
  height: calc(100% + 16cqi);
  overflow: visible;
  transform: rotate(-90deg);
}
.table-glyph__arc:has(rect) {
  transform: none;
}
.table-glyph__arc-track,
.table-glyph__arc-value {
  fill: none;
  stroke-width: 2;
}
.table-glyph__arc-track {
  stroke: color-mix(in srgb, var(--glyph-timer) 14%, transparent);
}
.table-glyph__arc-value {
  stroke: var(--glyph-timer);
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 650ms, stroke 400ms;
}
.table-glyph--mini .table-glyph__arc {
  top: -5cqi;
  left: -5cqi;
  width: calc(100% + 10cqi);
  height: calc(100% + 10cqi);
}
.table-glyph__body {
  position: absolute;
  inset: 0;
  box-sizing: border-box;
  border: 2px solid var(--table-edge);
  border-radius: 10px;
  background: var(--table-bg);
  box-shadow: var(--ep-shadow-xs);
  transition: background-color 420ms, border-color 420ms;
}
.table-glyph[data-shape='round'] .table-glyph__body {
  border-radius: 50%;
}
@media (prefers-reduced-motion: reduce) {
  .table-glyph__seat,
  .table-glyph__body,
  .table-glyph__arc-value {
    transition: none;
  }
}
</style>
