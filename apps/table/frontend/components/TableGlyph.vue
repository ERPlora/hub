<script setup lang="ts">
import { computed } from 'vue';

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

const spots = computed(() => seatSpots(props.table.capacity, props.table.shape, props.table.width / props.table.height));
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
    <svg
      v-if="table.status === 'occupied'"
      class="table-glyph__arc"
      :data-tone="tone"
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
    >
      <template v-if="table.shape === 'round'">
        <circle class="table-glyph__arc-track" cx="50" cy="50" r="48" pathLength="100" vector-effect="non-scaling-stroke" />
        <circle class="table-glyph__arc-value" cx="50" cy="50" r="48" pathLength="100" vector-effect="non-scaling-stroke" :stroke-dasharray="dash" />
      </template>
      <template v-else>
        <rect class="table-glyph__arc-track" x="1" y="1" width="98" height="98" rx="14" pathLength="100" vector-effect="non-scaling-stroke" />
        <rect class="table-glyph__arc-value" x="1" y="1" width="98" height="98" rx="14" pathLength="100" vector-effect="non-scaling-stroke" :stroke-dasharray="dash" />
      </template>
    </svg>
  </div>
</template>

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
  inset: -8cqi;
  width: 116cqi;
  height: 116cqi;
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
  inset: -5cqi;
  width: 110cqi;
  height: 110cqi;
}
@media (prefers-reduced-motion: reduce) {
  .table-glyph__seat,
  .table-glyph__arc-value {
    transition: none;
  }
}
</style>
