<script setup lang="ts">
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import { roomSummary, zoneCounts } from '../lib/floor-summary';
import type { TableOut, ZoneOut } from '../operations';

const props = defineProps<{
  zone: ZoneOut | null;
  /** The zone's tables in service, as the plan paints them now. */
  tables: TableOut[];
}>();

const t = useT();
const counts = computed(() => zoneCounts(props.tables));
const sums = computed(() => roomSummary(props.tables));
const stats = computed(() => [
  { key: 'available', icon: 'ion:checkmark-circle-outline', value: sums.value.available },
  { key: 'occupied', icon: 'ion:people-outline', value: sums.value.occupied },
  { key: 'reserved', icon: 'ion:time-outline', value: sums.value.reserved },
  { key: 'guests', icon: 'ion:person-outline', value: sums.value.guests },
]);
const zoneColor = computed(() => (props.zone ? `var(--ion-color-${props.zone.color})` : 'var(--ion-color-primary)'));
</script>

<template>
  <section
    class="floor-summary"
    data-testid="table-floor-summary"
    :aria-label="$t('table.floor.summary.label')"
    :style="{ '--zone-color': zoneColor }"
  >
    <div class="floor-summary__zone">
      <h2>{{ zone?.name }}</h2>
      <p data-part="occupied-of">
        {{ t('table.floor.summary.occupiedOf', { occupied: counts.occupied, count: counts.total }) }}
      </p>
    </div>
    <div class="floor-summary__stats">
      <div
        v-for="stat in stats"
        :key="stat.key"
        class="floor-summary__stat"
        :data-stat="stat.key"
      >
        <HubIcon
          class="floor-summary__icon"
          :name="stat.icon"
        />
        <div>
          <strong>{{ stat.value }}</strong>
          <span>{{ $t(`table.floor.summary.${stat.key}`) }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.floor-summary {
  display: flex;
  flex: none;
  align-items: center;
  gap: 20px;
  min-height: 76px;
  margin: 10px 0;
  padding: 12px 16px;
  border: 1px solid var(--ion-border-color);
  border-radius: var(--ep-radius-lg);
  background: var(--ion-card-background);
  box-shadow: var(--ep-shadow-sm);
}
.floor-summary__zone {
  min-width: 150px;
  padding-left: 11px;
  border-left: 3px solid var(--zone-color);
}
.floor-summary__zone h2 {
  margin: 0;
  font-size: 18px;
  letter-spacing: -0.03em;
}
.floor-summary__zone p {
  margin: 4px 0 0;
  color: var(--ep-text-muted);
  font-size: 10px;
}
.floor-summary__stats {
  display: grid;
  flex: 1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.floor-summary__stat {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}
.floor-summary__icon {
  flex: none;
  font-size: 18px;
  color: var(--ep-text-muted);
}
.floor-summary__stat[data-stat='available'] .floor-summary__icon {
  color: var(--ep-success-text);
}
.floor-summary__stat[data-stat='occupied'] .floor-summary__icon {
  color: var(--ep-primary-text);
}
.floor-summary__stat[data-stat='reserved'] .floor-summary__icon {
  color: var(--ep-warning-text);
}
.floor-summary__stat strong {
  display: block;
  font-size: 17px;
  font-variant-numeric: tabular-nums;
  line-height: 1.1;
}
.floor-summary__stat span {
  display: block;
  margin-top: 3px;
  color: var(--ep-text-muted);
  font-size: 9px;
  white-space: nowrap;
}
@media (max-width: 640px) {
  .floor-summary {
    min-height: 70px;
    margin: 8px 0;
    padding: 10px;
    gap: 8px;
  }
  .floor-summary__zone,
  .floor-summary__icon {
    display: none;
  }
  .floor-summary__stats {
    gap: 5px;
  }
  .floor-summary__stat {
    justify-content: center;
    gap: 5px;
    text-align: center;
  }
  .floor-summary__stat strong {
    font-size: 15px;
  }
  .floor-summary__stat span {
    font-size: 8px;
  }
}
</style>
