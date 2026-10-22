<script setup lang="ts">
// The bell at the end of the topbar (BASE-G137; the old hub's, hub#1678): `base.bell.counters`, live — a write
// anywhere in the business re-runs it on the server, so it no longer asks every 30 s. The badge sums the counters
// above zero; opened, one row per counter («Failed events (2)») that leads to its screen when this hub has it.
// A failed read keeps the last counters (`useLive` keeps its data); one that never came says so.
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonItem, IonLabel, IonList, IonPopover } from '@ionic/vue';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import type { BellCounter } from '../operations';
import { useBaseI18n } from '../lib/i18n';

const { t } = useBaseI18n();
const router = useRouter();
const { data, status } = useLive('base.bell.counters', {});
const open = ref(false);
const anchor = ref<Event | undefined>();

const counters = computed<BellCounter[]>(() => data.value?.counters ?? []);
const total = computed(() => counters.value.reduce((sum, counter) => sum + counter.count, 0));
const failed = computed(() => data.value === undefined && status.value === 'error');

/** A route the router has (its hash aside): one that falls on the 404 leads nowhere. */
const reachable = (route: string) => route !== '' && router.resolve(route).name !== 'not-found';

function show(event: Event): void {
  anchor.value = event;
  open.value = true;
}

function go(counter: BellCounter): void {
  if (!reachable(counter.route)) return;
  open.value = false;
  void router.push(counter.route);
}
</script>

<template>
  <ion-button
    class="hub-bell"
    data-testid="hub-bell"
    :aria-label="t('base.bell.title')"
    :title="t('base.bell.title')"
    @click="show"
  >
    <HubIcon
      slot="icon-only"
      name="ion:notifications-outline"
    />
    <ion-badge
      v-if="total > 0"
      color="danger"
      class="hub-bell-badge"
      data-testid="hub-bell-badge"
    >
      {{ total }}
    </ion-badge>
  </ion-button>
  <ion-popover
    :is-open="open"
    :event="anchor"
    :aria-label="t('base.bell.title')"
    @did-dismiss="open = false"
  >
    <p
      v-if="failed"
      class="hub-bell-note"
      data-testid="hub-bell-error"
    >
      {{ $t('base.bell.loadError') }}
    </p>
    <p
      v-else-if="counters.length === 0"
      class="hub-bell-note"
      data-testid="hub-bell-empty"
    >
      {{ $t('base.bell.empty') }}
    </p>
    <ion-list
      v-else
      lines="full"
    >
      <ion-item
        v-for="counter in counters"
        :key="counter.key"
        :button="reachable(counter.route)"
        :detail="false"
        data-testid="hub-bell-row"
        :data-reachable="String(reachable(counter.route))"
        @click="go(counter)"
      >
        <HubIcon
          slot="start"
          :name="counter.icon || 'ion:notifications-outline'"
        />
        <ion-label>{{ counter.label }} ({{ counter.count }})</ion-label>
      </ion-item>
    </ion-list>
  </ion-popover>
</template>

<style scoped>
.hub-bell {
  position: relative;
}

.hub-bell-badge {
  position: absolute;
  top: 2px;
  inset-inline-end: 0;
  min-width: 16px;
  padding: 2px 4px;
  font-size: 10px;
}

.hub-bell-note {
  margin: 0;
  padding: 16px;
  color: var(--ion-color-medium);
}
</style>
