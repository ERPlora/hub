<script setup lang="ts">
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, nextTick, useTemplateRef, watch } from 'vue';

import { useScrollEdges } from '../composables/useScrollEdges';
import { zoneCounts } from '../lib/floor-summary';
import type { TableOut, ZoneOut } from '../operations';

const props = defineProps<{
  zones: ZoneOut[];
  active: string | null;
  /** Every table as the plan paints it now, from every zone. */
  tables: TableOut[];
}>();

const emit = defineEmits<{ change: [zoneId: string] }>();

const counts = computed(() => new Map(props.zones.map((zone) => [zone.id, zoneCounts(props.tables.filter((table) => table.zone_id === zone.id))])));

function onChange(event: CustomEvent<{ value?: string | number }>): void {
  const value = event.detail.value;
  if (value !== undefined && value !== null) emit('change', String(value));
}

// The strip fades the edge with more zones behind it: a hard cut reads «no more zones».
const strip = useTemplateRef<InstanceType<typeof IonSegment>>('strip');
const { edges, mark } = useScrollEdges(computed(() => (strip.value?.$el as HTMLElement | undefined) ?? null));
// Zones added or renamed widen the strip without resizing it.
watch(
  () => props.zones,
  () => void nextTick(mark),
);
</script>

<template>
  <ion-segment
    ref="strip"
    class="table-floor__zones"
    :class="{ 'table-floor__zones--more-left': edges.left, 'table-floor__zones--more-right': edges.right }"
    data-testid="table-floor-zones"
    scrollable
    :value="active ?? undefined"
    :aria-label="$t('table.floor.zones')"
    @ion-change="onChange"
  >
    <ion-segment-button
      v-for="zone in zones"
      :key="zone.id"
      :value="zone.id"
      :data-testid="`table-floor-zone-tab-${zone.id}`"
    >
      <ion-label>
        <span
          class="zone-tab"
          :style="{ '--zone-color': `var(--ion-color-${zone.color})` }"
        >
          <span
            class="zone-tab__dot"
            aria-hidden="true"
          />
          <span data-part="zone-name">{{ zone.name }}</span>
          <span
            class="zone-tab__count"
            data-part="zone-count"
            aria-hidden="true"
          >{{ counts.get(zone.id)?.occupied }}/{{ counts.get(zone.id)?.total }}</span>
          <span
            class="zone-tab__said"
            data-part="zone-count-said"
          >{{ $t('table.floor.summary.occupiedOf', { occupied: counts.get(zone.id)?.occupied, count: counts.get(zone.id)?.total }) }}</span>
        </span>
      </ion-label>
    </ion-segment-button>
  </ion-segment>
</template>

<style scoped>
.table-floor__zones {
  flex: 1 1 auto;
  min-width: 0;
}
.table-floor__zones ion-segment-button {
  min-width: 112px;
}
.table-floor__zones--more-right {
  -webkit-mask-image: linear-gradient(to right, #000 calc(100% - 1.5rem), transparent);
  mask-image: linear-gradient(to right, #000 calc(100% - 1.5rem), transparent);
}
.table-floor__zones--more-left {
  -webkit-mask-image: linear-gradient(to left, #000 calc(100% - 1.5rem), transparent);
  mask-image: linear-gradient(to left, #000 calc(100% - 1.5rem), transparent);
}
.table-floor__zones--more-left.table-floor__zones--more-right {
  -webkit-mask-image: linear-gradient(to right, transparent, #000 1.5rem, #000 calc(100% - 1.5rem), transparent);
  mask-image: linear-gradient(to right, transparent, #000 1.5rem, #000 calc(100% - 1.5rem), transparent);
}
.zone-tab {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
}
.zone-tab__dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--zone-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--zone-color) 12%, transparent);
}
.zone-tab__count {
  color: var(--ep-text-muted);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  font-weight: 650;
}
.zone-tab__said {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
</style>
