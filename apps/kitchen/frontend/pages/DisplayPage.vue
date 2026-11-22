<script setup lang="ts">
// Kitchen → Display (WORKBOOK «Pantallas · Pantalla»; KITCHEN-F10 to F16), as the old KDS: one bar, sticky,
// with the three views and their counts, «Full screen» and the stations (remembered on this device). Then the grid
// of cards (as many equal columns as fit; one on a phone) or the All-Day table. Everything is live
// (`kitchen.ticket.board`, `.all_day`, `kitchen.settings.get`); every action goes to the server scoped to the station
// chosen, and the screen follows what comes back. It rings for a ticket that arrives or turns rush, never for what
// was there when it opened.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, effectScope, type EffectScope, onBeforeUnmount, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue';

import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';
import KdsAllDayTable from '../components/KdsAllDayTable.vue';
import KdsBoardSkeleton from '../components/KdsBoardSkeleton.vue';
import KdsDisplayToolbar, { type DisplayView } from '../components/KdsDisplayToolbar.vue';
import KdsTicket from '../components/KdsTicket.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useNow } from '../composables/useNow';
import { useT } from '../composables/useT';
import { arrivals, rememberedStation, rememberStation } from '../lib/board';
import { Chime } from '../lib/chime';
import type { AllDayOut, Priority, SettingsOut, TicketOut } from '../operations';

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
const tabs = useAppTabs('kitchen');
const t = useT();
const now = useNow();
const canChange = computed(() => session.can('kitchen.change_ticket'));
const canServe = computed(() => session.can('kitchen.complete_ticket'));

const view = ref<DisplayView>('tickets');
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
const counts = computed(() => ({ tickets: board.value?.cooking_count ?? 0, ready: board.value?.ready_count ?? 0 }));

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

const shown = computed(() => (view.value === 'ready' ? ready.value : cooking.value));
const emptyKey = computed(() => (view.value === 'ready' ? 'kitchen.display.emptyReady' : 'kitchen.display.emptyTickets'));
</script>

<template>
  <AppPage
    :title="$t('kitchen.title')"
    :tabs="tabs"
    :tabs-label="$t('kitchen.tabs.label')"
  >
    <div
      ref="root"
      class="kds"
      :class="{ 'kds--fullscreen': fullscreen }"
      data-testid="kitchen-display"
    >
      <KdsDisplayToolbar
        v-model:view="view"
        v-model:station="station"
        :stations="chips"
        :counts="counts"
        :fullscreen-offered="fullscreenOffered"
        :fullscreen="fullscreen"
        @fullscreen="toggleFullscreen"
      />
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
      <KdsBoardSkeleton v-if="!board && !blocked && !failed" />
      <template v-else-if="board">
        <KdsAllDayTable
          v-if="view === 'allday'"
          :rows="allDay?.rows"
          :show-station="!station"
        />
        <div
          v-else-if="shown.length"
          class="ep-order-board"
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
/* Alone on the screen the display is the box that scrolls: the board's bar sticks over the top padding it declares. */
.kds--fullscreen {
  --padding-top: 0.75rem;
  background: var(--ion-background-color, #fff);
  padding: var(--padding-top) 0.75rem 0.75rem;
  overflow: auto;
}
</style>
