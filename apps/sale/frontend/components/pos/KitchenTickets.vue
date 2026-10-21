<script setup lang="ts">
// «Tickets · N» in the head of what the check sent (KITCHEN-F19, F20; SALE-F20): the check's kitchen tickets,
// live (`kitchen.ticket.by_order`, by the name of Kitchen's operation: Sales does not require Kitchen), and
// «Order tickets», a card per round in the kitchen's order (the newest round first) with the time in the
// business's zone (`kitchen.settings.get`). Nothing shows while they load or while the kitchen has none. «Mark
// rush» rushes a round through `kitchen.ticket.set_rush`: a refusal is read on top of the sheet, and a rush whose
// notice did not print says so until a later rush prints. The cart mounts it only with Kitchen on and the right
// to see its tickets (`useLive` has no «skip»).
import { useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
import { refusal } from '../../lib/refusal';
import KitchenTicketCard from './KitchenTicketCard.vue';
import PosSheet from './PosSheet.vue';

const props = defineProps<{ orderId: string }>();

/** The business's zone until the kitchen says it (the one the kitchen itself falls back to). */
const BUSINESS_ZONE = 'Europe/Madrid';

const t = useT();
const session = useSession();

const { data, error, refresh } = useLive('kitchen.ticket.by_order', () => ({ order_id: props.orderId }));
const { data: settings } = useLive('kitchen.settings.get', {});
const setRush = useCommand('kitchen.ticket.set_rush');

const tickets = computed(() => data.value?.tickets ?? []);
const timeZone = computed(() => settings.value?.timezone || BUSINESS_ZONE);
const canRush = computed(() => session.can('kitchen.change_ticket'));

const open = shallowRef(false);
const busy = shallowRef<ReadonlySet<string>>(new Set());
const refused = shallowRef<string | null>(null);
const unprinted = shallowRef(false);

function setBusy(ticketId: string, on: boolean): void {
  const next = new Set(busy.value);
  if (on) next.add(ticketId);
  else next.delete(ticketId);
  busy.value = next;
}

async function rush(ticketId: string, on: boolean): Promise<void> {
  refused.value = null;
  setBusy(ticketId, true);
  try {
    const answer = await setRush.run({ ticket_id: ticketId, rush: on });
    // Only a rush prints a notice: taking it away says nothing about the printer.
    if (on) unprinted.value = !!answer.print_error;
  } catch (failure) {
    refused.value = refusal(failure, t('sale.pos.kitchen.tickets.rushFailed'))?.message ?? t('sale.pos.kitchen.tickets.rushFailed');
  } finally {
    setBusy(ticketId, false);
  }
}
</script>

<template>
  <button
    v-if="tickets.length"
    type="button"
    class="pos-ktickets__open"
    :aria-label="t('sale.pos.kitchen.tickets.title')"
    :title="t('sale.pos.kitchen.tickets.title')"
    data-testid="pos-kitchen-tickets-open"
    @click="open = true"
  >
    <HubIcon name="ion:receipt-outline" />{{ t('sale.pos.kitchen.tickets.open', { count: tickets.length }) }}
  </button>
  <PosSheet
    v-model:open="open"
    :title="t('sale.pos.kitchen.tickets.title')"
    testid="pos-kitchen-tickets"
  >
    <div class="pos-ktickets">
      <div
        v-if="error"
        class="pos-ktickets__load-error"
        role="alert"
        data-testid="pos-kitchen-tickets-load-error"
      >
        <span>{{ t('sale.pos.kitchen.tickets.loadError') }}</span>
        <ion-button
          size="small"
          fill="outline"
          mode="md"
          data-testid="pos-kitchen-tickets-retry"
          @click="refresh()"
        >
          {{ t('sale.pos.kitchen.tickets.retry') }}
        </ion-button>
      </div>
      <p
        v-if="refused"
        class="pos-ktickets__error"
        role="alert"
        data-testid="pos-kitchen-tickets-error"
      >
        {{ refused }}
      </p>
      <p
        v-if="unprinted"
        class="pos-ktickets__warning"
        role="status"
        data-testid="pos-kitchen-tickets-print-warning"
      >
        {{ t('sale.pos.kitchen.tickets.rushNoticeFailed') }}
      </p>
      <KitchenTicketCard
        v-for="ticket in tickets"
        :key="ticket.id"
        :ticket="ticket"
        :can-rush="canRush"
        :busy="busy.has(ticket.id)"
        :time-zone="timeZone"
        @rush="rush(ticket.id, $event)"
      />
    </div>
  </PosSheet>
</template>

<style scoped>
.pos-ktickets__open {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 0.3rem;
  margin-left: auto;
  min-height: 2rem;
  padding: 0.2rem 0.65rem;
  font: inherit;
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: none;
  color: var(--ion-color-primary, #0091ce);
  background: transparent;
  border: 1px solid var(--ion-color-primary, #0091ce);
  border-radius: 999px;
  cursor: pointer;
}
.pos-ktickets {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.pos-ktickets__load-error {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  color: var(--ion-color-danger, #c5000f);
  font-size: 0.85rem;
}
.pos-ktickets__error {
  margin: 0;
  color: var(--ion-color-danger, #c5000f);
  font-size: 0.85rem;
}
.pos-ktickets__warning {
  margin: 0;
  color: var(--ion-color-warning-shade, #b26b00);
  font-size: 0.85rem;
}
</style>
