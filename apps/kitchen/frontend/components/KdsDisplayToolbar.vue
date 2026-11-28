<script lang="ts">
export type DisplayView = 'tickets' | 'ready' | 'allday';
</script>

<script setup lang="ts">
// The bar of the kitchen display, sticky while the board scrolls: the views, «Full screen» and the stations.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed } from 'vue';

import type { StationChipOut } from '../operations/board';

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
  <div class="ep-order-board-bar">
    <div class="ep-order-board-bar__main">
      <ion-segment
        class="ep-order-board-bar__views"
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
              class="ep-order-board-bar__count"
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
              class="ep-order-board-bar__count"
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
        class="ep-order-board-bar__fullscreen"
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
      class="ep-order-board-bar__stations"
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
            class="ep-station-dot"
            :style="{ background: chip.color }"
          />{{ chip.id ? chip.name : $t('kitchen.display.stationNone') }}
        </ion-label>
      </ion-segment-button>
    </ion-segment>
  </div>
</template>

