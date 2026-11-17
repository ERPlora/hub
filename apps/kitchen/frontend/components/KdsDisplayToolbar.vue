<script lang="ts">
export type DisplayView = 'tickets' | 'ready' | 'allday';
</script>

<script setup lang="ts">
// The bar of the kitchen display, sticky while the board scrolls: the views, «Full screen» and the stations.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed } from 'vue';

import type { StationChipOut } from '../operations';

const VIEWS: readonly DisplayView[] = ['tickets', 'ready', 'allday'];
const ALL = '__all';

const props = defineProps<{
  view: DisplayView;
  /** `''`: every station (the pass); `none`: the dishes with no station; else a station's id. */
  station: string;
  stations: StationChipOut[];
  counts: { tickets: number; ready: number };
  fullscreenOffered: boolean;
  fullscreen: boolean;
}>();

const emit = defineEmits<{
  'update:view': [view: DisplayView];
  'update:station': [station: string];
  fullscreen: [];
}>();

const showStations = computed(() => props.stations.length > 1 || props.station !== '');

function onView(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? 'tickets') as DisplayView;
  if (VIEWS.includes(value)) emit('update:view', value);
}

function onStation(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? ALL);
  emit('update:station', value === ALL ? '' : value);
}
</script>

<template>
  <div class="kds-bar">
    <div class="kds-bar__main">
      <ion-segment
        class="kds-bar__views"
        data-testid="kitchen-display-views"
        :value="view"
        :aria-label="$t('kitchen.display.views.label')"
        @ion-change="onView"
      >
        <ion-segment-button
          value="tickets"
          data-testid="kitchen-display-view-tickets"
        >
          <ion-label>
            {{ $t('kitchen.display.views.tickets') }}
            <span
              class="kds-bar__count"
              data-testid="kitchen-display-count-tickets"
            >{{ counts.tickets }}</span>
          </ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="ready"
          data-testid="kitchen-display-view-ready"
        >
          <ion-label>
            {{ $t('kitchen.display.views.ready') }}
            <span
              class="kds-bar__count"
              data-testid="kitchen-display-count-ready"
            >{{ counts.ready }}</span>
          </ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="allday"
          data-testid="kitchen-display-view-allday"
        >
          <ion-label>{{ $t('kitchen.display.views.allDay') }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <ion-button
        v-if="fullscreenOffered"
        fill="outline"
        color="medium"
        class="kds-bar__fullscreen"
        data-testid="kitchen-display-fullscreen"
        :aria-label="fullscreen ? $t('kitchen.display.exitFullscreen') : $t('kitchen.display.fullscreen')"
        :title="fullscreen ? $t('kitchen.display.exitFullscreen') : $t('kitchen.display.fullscreen')"
        @click="emit('fullscreen')"
      >
        <HubIcon
          slot="icon-only"
          name="ion:chevron-expand-outline"
        />
      </ion-button>
    </div>
    <ion-segment
      v-if="showStations"
      class="kds-bar__stations"
      data-testid="kitchen-display-stations"
      scrollable
      :value="station || ALL"
      :aria-label="$t('kitchen.display.stationsLabel')"
      @ion-change="onStation"
    >
      <ion-segment-button
        :value="ALL"
        data-testid="kitchen-display-station-all"
      >
        <ion-label>{{ $t('kitchen.display.stationAll') }}</ion-label>
      </ion-segment-button>
      <ion-segment-button
        v-for="chip in stations"
        :key="chip.id ?? 'none'"
        :value="chip.id ?? 'none'"
        :data-testid="`kitchen-display-station-${chip.id ?? 'none'}`"
      >
        <ion-label>
          <i
            v-if="chip.color"
            class="kds-bar__dot"
            :style="{ background: chip.color }"
          />{{ chip.id ? chip.name : $t('kitchen.display.stationNone') }}
        </ion-label>
      </ion-segment-button>
    </ion-segment>
  </div>
</template>

<style scoped>
.kds-bar {
  container-type: inline-size;
  position: sticky;
  top: 0;
  z-index: 2;
  margin-bottom: 0.75rem;
  padding: 0 0 0.5rem;
  border-bottom: 1px solid var(--ion-border-color);
  background: var(--ion-background-color);
}
.kds-bar__main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}
/* The views never shrink below their words: on a narrow bar «Full screen» wraps instead of a tab being clipped. */
.kds-bar__views {
  flex: 1 1 auto;
  width: auto;
  min-width: fit-content;
  max-width: 32rem;
}
.kds-bar__stations {
  width: 100%;
  margin-top: 0.4rem;
}
.kds-bar ion-segment-button {
  min-width: 48px;
  min-height: 48px;
  --padding-start: 0.6rem;
  --padding-end: 0.6rem;
  text-transform: none;
}
.kds-bar ion-label {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  white-space: nowrap;
}
.kds-bar__count {
  min-width: 1.6rem;
  padding: 0.1rem 0.45rem;
  border-radius: var(--ep-radius-pill);
  background: var(--ion-color-step-100);
  color: var(--ion-text-color);
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.kds-bar__fullscreen {
  flex: none;
  width: 48px;
  min-height: 48px;
  margin: 0;
  font-size: 1.3rem;
  --padding-start: 0;
  --padding-end: 0;
  --border-radius: 12px;
}
@container (max-width: 26rem) {
  .kds-bar ion-segment-button {
    --padding-start: 0.3rem;
    --padding-end: 0.3rem;
  }
  .kds-bar ion-label {
    gap: 0.25rem;
    font-size: 0.8rem;
  }
  .kds-bar__count {
    min-width: 1.4rem;
    padding: 0.1rem 0.3rem;
  }
}
.kds-bar__dot {
  flex: none;
  width: 0.65rem;
  height: 0.65rem;
  border-radius: 50%;
}
</style>
