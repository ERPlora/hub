<script setup lang="ts">
// Kitchen → Display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F16), as the old KDS: one bar, sticky,
// with the three views and their counts («Tickets», «Ready», «All-Day»), «Full screen» when the device
// offers it and, with dishes of more than one station (or one chosen), the station buttons — remembered on
// this device. Then the grid of cards (equal columns; one on a phone) or the All-Day table. Everything is
// live (`kitchen.ticket.board`, `.all_day`, `kitchen.settings.get`); every action goes to the server scoped
// to the station chosen, and the screen follows what comes back. It rings for a ticket that arrives or turns
// rush, never for what was there when it opened.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, effectScope, type EffectScope, onBeforeUnmount, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue';

import KdsTicket from '../components/KdsTicket.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useNow } from '../composables/useNow';
import { useLocale, useT } from '../composables/useT';
import { arrivals, rememberedStation, rememberStation } from '../lib/board';
import { Chime } from '../lib/chime';
import { formatQuantity } from '../lib/format';
import type { AllDayOut, Priority, SettingsOut, TicketOut } from '../operations';
import { kitchenTabs } from '../tabs';

type View = 'tickets' | 'ready' | 'allday';
const VIEWS: readonly View[] = ['tickets', 'ready', 'allday'];
const ALL = '__all';
const FACTORY: SettingsOut = {
  show_timer: true,
  warning_minutes: 15,
  critical_minutes: 30,
  color_coding: true,
  sound_enabled: true,
  sound_volume: 70,
  sound_tone: 'chime',
  print_pass: false,
  works_from_screen: true,
  default_order_type: 'dine_in',
  timezone: 'Europe/Madrid',
};

const session = useSession();
const t = useT();
const locale = useLocale();
const now = useNow();
const canChange = computed(() => session.can('kitchen.change_ticket'));
const canServe = computed(() => session.can('kitchen.complete_ticket'));

const view = ref<View>('tickets');
/** `''`: every station (the pass); `none`: the dishes with no station; else a station's id. */
const station = ref(rememberedStation());
const params = () => (station.value ? { station: station.value } : {});

const { data: board, status, error, refresh } = useLive('kitchen.ticket.board', params);
// What is left to cook is followed only while «All-Day» is open: one live query less per display.
const client = useLiveClient();
let allDayScope: EffectScope | null = null;
const allDay = shallowRef<AllDayOut | undefined>(undefined);
watch(
  view,
  (now) => {
    if (now === 'allday' && !allDayScope) {
      allDayScope = effectScope();
      allDayScope.run(() => {
        const live = useLive('kitchen.ticket.all_day', params, { client });
        watch(live.data, (data) => (allDay.value = data), { immediate: true });
      });
    } else if (now !== 'allday' && allDayScope) {
      allDayScope.stop();
      allDayScope = null;
      allDay.value = undefined;
    }
  },
  { immediate: true },
);
onScopeDispose(() => allDayScope?.stop());
const { data: settingsData } = useLive('kitchen.settings.get', {});
const settings = computed(() => settingsData.value ?? FACTORY);
const blocked = computed(() => blockingError(error.value));
const failed = computed(() => status.value === 'error' && !!error.value && !blocked.value);
// The station this device remembers no longer exists (or never did): back to every station.
watch(error, (now) => {
  if (now?.code === 'kitchen.station_not_found' && station.value) station.value = '';
});

const cooking = computed(() => board.value?.cooking ?? []);
const ready = computed(() => board.value?.ready ?? []);
const chips = computed(() => board.value?.stations ?? []);
const showStations = computed(() => chips.value.length > 1 || station.value !== '');

// ── Sound (KITCHEN-F16) ──────────────────────────────────────────────────────────────────────────

const chime = new Chime();
let known: Map<string, Priority> | undefined;
watch(station, (value) => {
  rememberStation(value);
  known = undefined;
});
watch([cooking, ready], ([tickets, waiting]) => {
  if (!board.value) return;
  const next = arrivals(known, tickets, waiting);
  known = next.known;
  if (next.ring && settings.value.sound_enabled) {
    chime.play({ tone: settings.value.sound_tone, volume: settings.value.sound_volume });
  }
});

// ── Full screen ──────────────────────────────────────────────────────────────────────────────────

const root = ref<HTMLElement | null>(null);
const fullscreenOffered = typeof document !== 'undefined' && document.fullscreenEnabled === true;
const fullscreen = ref(false);
const onFullscreen = () => {
  fullscreen.value = document.fullscreenElement === root.value && root.value !== null;
};
onMounted(() => document.addEventListener('fullscreenchange', onFullscreen));
onBeforeUnmount(() => document.removeEventListener('fullscreenchange', onFullscreen));

async function toggleFullscreen(): Promise<void> {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await root.value?.requestFullscreen();
}

// ── Actions ──────────────────────────────────────────────────────────────────────────────────────

const bump = useCommand('kitchen.item.bump');
const recallItems = useCommand('kitchen.item.recall');
const rush = useCommand('kitchen.ticket.set_rush');
const serve = useCommand('kitchen.ticket.serve');
const actionError = ref<ApiError | null>(null);
const passWarning = ref(false);
const rushWarning = ref(false);
const scope = () => (station.value ? { station: station.value } : {});

async function act(run: () => Promise<TicketOut>, after?: (ticket: TicketOut) => void): Promise<void> {
  actionError.value = null;
  try {
    const ticket = await run();
    after?.(ticket);
  } catch (refused) {
    actionError.value = refused as ApiError;
  }
}

const afterBump = (ticket: TicketOut) => {
  // The pass prints when a ticket turns ready: the warning stays until a later pass comes out.
  if (ticket.status === 'ready') passWarning.value = !!ticket.print_error;
};

function onBump(ticket: TicketOut, itemIds: string[]): void {
  void act(() => bump.run({ ticket_id: ticket.id, item_ids: itemIds, ...scope() }), afterBump);
}

function onRecall(ticket: TicketOut, itemIds: string[]): void {
  void act(() => recallItems.run({ ticket_id: ticket.id, item_ids: itemIds, ...scope() }));
}

function onRush(ticket: TicketOut, value: boolean): void {
  void act(
    () => rush.run({ ticket_id: ticket.id, rush: value }),
    (answer) => {
      if (value) rushWarning.value = !!answer.print_error;
    },
  );
}

function onServe(ticket: TicketOut): void {
  void act(() => serve.run({ ticket_id: ticket.id }));
}

function onView(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? 'tickets') as View;
  if (VIEWS.includes(value)) view.value = value;
}

function onStation(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? ALL);
  station.value = value === ALL ? '' : value;
}

const shown = computed(() => (view.value === 'ready' ? ready.value : cooking.value));
const emptyKey = computed(() => (view.value === 'ready' ? 'kitchen.display.emptyReady' : 'kitchen.display.emptyTickets'));
</script>

<template>
  <AppPage
    :title="$t('kitchen.title')"
    :tabs="kitchenTabs($t, { settings: session.can('kitchen.change_settings') })"
    :tabs-label="$t('kitchen.tabs.label')"
  >
    <div
      ref="root"
      class="kds"
      :class="{ 'kds--fullscreen': fullscreen }"
      data-testid="kitchen-display"
    >
      <div class="kds__bar">
        <ion-segment
          class="kds__views"
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
                class="kds__count"
                data-testid="kitchen-display-count-tickets"
              >{{ board?.cooking_count ?? 0 }}</span>
            </ion-label>
          </ion-segment-button>
          <ion-segment-button
            value="ready"
            data-testid="kitchen-display-view-ready"
          >
            <ion-label>
              {{ $t('kitchen.display.views.ready') }}
              <span
                class="kds__count"
                data-testid="kitchen-display-count-ready"
              >{{ board?.ready_count ?? 0 }}</span>
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
          class="kds__fullscreen"
          data-testid="kitchen-display-fullscreen"
          :aria-label="fullscreen ? $t('kitchen.display.exitFullscreen') : $t('kitchen.display.fullscreen')"
          :title="fullscreen ? $t('kitchen.display.exitFullscreen') : $t('kitchen.display.fullscreen')"
          @click="toggleFullscreen"
        >
          <HubIcon name="ion:chevron-expand-outline" />
        </ion-button>
        <ion-segment
          v-if="showStations"
          class="kds__stations"
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
            v-for="chip in chips"
            :key="chip.id ?? 'none'"
            :value="chip.id ?? 'none'"
            :data-testid="`kitchen-display-station-${chip.id ?? 'none'}`"
          >
            <ion-label>
              <i
                v-if="chip.color"
                class="kds__dot"
                :style="{ background: chip.color }"
              />{{ chip.id ? chip.name : $t('kitchen.display.stationNone') }}
            </ion-label>
          </ion-segment-button>
        </ion-segment>
      </div>
      <PageNotices
        testid="kitchen-display"
        :status="status"
        :error="error"
      />
      <InlineFeedback
        v-if="failed"
        tone="danger"
        data-testid="kitchen-display-error"
        :heading="$t('kitchen.display.loadError')"
      >
        {{ error?.message }}
        <ion-button
          size="small"
          fill="outline"
          data-testid="kitchen-display-retry"
          @click="refresh()"
        >
          {{ $t('kitchen.live.retry') }}
        </ion-button>
      </InlineFeedback>
      <InlineFeedback
        v-if="actionError"
        tone="danger"
        data-testid="kitchen-display-action-error"
        :heading="$t('kitchen.display.actionError')"
      >
        {{ actionError.message }}
      </InlineFeedback>
      <InlineFeedback
        v-if="passWarning"
        tone="warning"
        data-testid="kitchen-display-pass-warning"
      >
        {{ $t('kitchen.display.passPrintFailed') }}
      </InlineFeedback>
      <InlineFeedback
        v-if="rushWarning"
        tone="warning"
        data-testid="kitchen-display-rush-warning"
      >
        {{ $t('kitchen.display.rushNoticeFailed') }}
      </InlineFeedback>
      <InlineFeedback
        v-if="board?.truncated"
        tone="warning"
        data-testid="kitchen-display-truncated"
      >
        {{ $t('kitchen.display.truncated') }}
      </InlineFeedback>
      <p
        v-if="!board && !blocked && !failed"
        class="kds__loading"
        data-testid="kitchen-display-loading"
      >
        {{ $t('kitchen.display.loading') }}
      </p>
      <template v-else-if="board">
        <template v-if="view === 'allday'">
          <table
            v-if="allDay?.rows.length"
            class="kds__allday"
            data-testid="kitchen-display-allday"
          >
            <thead>
              <tr>
                <th>{{ $t('kitchen.display.colDish') }}</th>
                <th v-if="!station">
                  {{ $t('kitchen.display.colStation') }}
                </th>
                <th class="kds__num">
                  {{ $t('kitchen.display.colLeft') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="dish in allDay.rows"
                :key="`${dish.product_id ?? dish.name}-${dish.station_id ?? 'none'}-${dish.unit}`"
              >
                <td>{{ dish.name }}</td>
                <td v-if="!station">
                  {{ dish.station_name || $t('kitchen.display.stationNone') }}
                </td>
                <td class="kds__num">
                  {{ formatQuantity(dish.quantity, locale) }}
                </td>
              </tr>
            </tbody>
          </table>
          <EmptyState
            v-else
            data-testid="kitchen-display-empty"
            icon="ion:checkmark-circle-outline"
            :heading="$t('kitchen.display.emptyAllDay')"
          />
        </template>
        <div
          v-else-if="shown.length"
          class="kds__grid"
          data-testid="kitchen-display-grid"
        >
          <KdsTicket
            v-for="ticket in shown"
            :key="ticket.id"
            :ticket="ticket"
            :now="now"
            :settings="settings"
            :show-station="!station"
            :can-change="canChange"
            :can-serve="canServe"
            @bump="onBump(ticket, $event)"
            @recall="onRecall(ticket, $event)"
            @rush="onRush(ticket, $event)"
            @serve="onServe(ticket)"
          />
        </div>
        <EmptyState
          v-else
          data-testid="kitchen-display-empty"
          icon="ion:checkmark-circle-outline"
          :heading="t(emptyKey)"
        />
      </template>
    </div>
  </AppPage>
</template>

<style scoped>
.kds {
  display: block;
}
.kds--fullscreen {
  background: var(--ion-background-color, #fff);
  padding: 0.75rem;
  overflow: auto;
}
.kds__bar {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  flex-wrap: wrap;
  padding: 0 0 0.4rem;
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--ion-background-color, #fff);
}
.kds__bar ion-segment {
  min-height: 44px;
}
.kds__views {
  width: auto;
  flex: 0 0 auto;
}
.kds__stations {
  width: auto;
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
}
.kds__bar ion-segment-button {
  min-height: 44px;
  --padding-start: 0.6rem;
  --padding-end: 0.6rem;
  text-transform: none;
}
.kds__count {
  font-variant-numeric: tabular-nums;
  opacity: 0.7;
  margin-left: 0.35rem;
}
.kds__fullscreen {
  min-width: 44px;
  min-height: 44px;
  margin: 0;
}
.kds__dot {
  display: inline-block;
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  margin-right: 0.35rem;
}
.kds__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(clamp(15rem, 22vw, 22rem), 1fr));
  gap: 0.6rem;
  align-items: start;
}
.kds__loading {
  opacity: 0.7;
}
.kds__allday {
  width: 100%;
  border-collapse: collapse;
  font-size: 1.2rem;
}
.kds__allday th,
.kds__allday td {
  text-align: left;
  padding: 0.5rem 0.75rem;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}
.kds__num {
  text-align: right !important;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
}
@media (max-width: 640px) {
  .kds__grid {
    grid-template-columns: 1fr;
  }
}
</style>
