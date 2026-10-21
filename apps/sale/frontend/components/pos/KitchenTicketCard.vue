<script setup lang="ts">
// One round of the check in «Order tickets» (KITCHEN-F19, F20): «Order N», the time it was sent in the
// business's zone, its state and «Rush» if it is; its dishes with their quantity (a dish the till voided after
// sending it, struck, with «Voided»); and, to whoever may change tickets, «Mark rush» / «Remove rush» while it
// cooks — a VIP round keeps its priority, so it never offers it. The words are the kitchen's (kitchen#112). The
// container rushes it (`rush`, with the way it goes).
import type { OutputOf } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatQuantity } from '../../lib/format';

type Ticket = OutputOf<'kitchen.ticket.by_order'>['tickets'][number];

const props = defineProps<{ ticket: Ticket; canRush: boolean; busy: boolean; timeZone: string }>();
const emit = defineEmits<{ rush: [rush: boolean] }>();

const t = useT();
const locale = useLocale();

const testid = computed(() => `pos-kitchen-ticket-${props.ticket.id}`);
const rushed = computed(() => props.ticket.priority === 'rush');
const cooking = computed(() => props.ticket.status === 'pending' || props.ticket.status === 'preparing');
const rushable = computed(() => props.canRush && cooking.value && props.ticket.priority !== 'vip');

const time = computed(() => {
  const moment = new Date(props.ticket.received_at);
  try {
    return new Intl.DateTimeFormat(locale.value, { timeStyle: 'short', timeZone: props.timeZone }).format(moment);
  } catch {
    // A zone the browser does not know: the device's own, never no time at all.
    return new Intl.DateTimeFormat(locale.value, { timeStyle: 'short' }).format(moment);
  }
});

const dishes = computed(() =>
  props.ticket.items.map((item) => ({
    id: item.id,
    status: item.status,
    voided: item.status === 'voided',
    text: `${formatQuantity(item.quantity, '', locale.value)}× ${item.name}`,
  })),
);
</script>

<template>
  <article
    class="pos-kticket"
    :class="{ 'pos-kticket--rush': rushed }"
    :data-testid="testid"
    :data-round="ticket.round_no"
  >
    <header class="pos-kticket__head">
      <span
        class="pos-kticket__round"
        :data-testid="`${testid}-round`"
      >{{ t('sale.pos.commandRound', { n: ticket.round_no }) }}</span>
      <span
        class="pos-kticket__time"
        :data-testid="`${testid}-time`"
      >{{ time }}</span>
      <span
        class="pos-kticket__status"
        :data-status="ticket.status"
        :data-testid="`${testid}-status`"
      >{{ t(`sale.pos.kitchen.tickets.status.${ticket.status}`) }}</span>
      <span
        v-if="rushed"
        class="pos-kticket__rush-mark"
        :data-testid="`${testid}-rush-mark`"
      >{{ t('sale.pos.kitchen.tickets.rush') }}</span>
    </header>
    <ul class="pos-kticket__dishes">
      <li
        v-for="dish in dishes"
        :key="dish.id"
        class="pos-kticket__dish"
        :class="{ 'pos-kticket__dish--voided': dish.voided }"
        :data-status="dish.status"
        :data-testid="`pos-kitchen-dish-${dish.id}`"
      >
        <span class="pos-kticket__dish-name">{{ dish.text }}</span>
        <span
          v-if="dish.voided"
          class="pos-kticket__voided"
          :data-testid="`pos-kitchen-dish-${dish.id}-voided`"
        >{{ t('sale.pos.kitchen.tickets.voided') }}</span>
      </li>
    </ul>
    <div
      v-if="rushable"
      class="pos-kticket__actions"
    >
      <button
        type="button"
        class="pos-kticket__rush"
        :class="{ 'pos-kticket__rush--on': rushed }"
        :aria-pressed="rushed ? 'true' : 'false'"
        :disabled="busy"
        :data-testid="`${testid}-rush`"
        @click="emit('rush', !rushed)"
      >
        {{ rushed ? t('sale.pos.kitchen.tickets.clearRush') : t('sale.pos.kitchen.tickets.markRush') }}
      </button>
    </div>
  </article>
</template>

<style scoped>
.pos-kticket {
  overflow: hidden;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
}
.pos-kticket--rush {
  border-color: var(--ion-color-danger, #c5000f);
}
.pos-kticket__head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.35rem 0.5rem;
  padding: 0.55rem 0.7rem;
  font-size: 0.85rem;
  border-bottom: 1px solid var(--ion-border-color, #e6e3db);
}
.pos-kticket__round {
  font-weight: 700;
}
.pos-kticket__time {
  color: var(--ion-color-medium, #8b897f);
  font-variant-numeric: tabular-nums;
}
.pos-kticket__status {
  margin-left: auto;
  padding: 0.1rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 600;
  border-radius: 999px;
  background: var(--ion-color-light, #f4f3ef);
}
.pos-kticket__status[data-status='ready'] {
  color: var(--ion-color-success-shade, #2a7a3b);
}
.pos-kticket__status[data-status='cancelled'] {
  color: var(--ion-color-medium, #8b897f);
}
.pos-kticket__rush-mark {
  padding: 0.1rem 0.5rem;
  font-size: 0.75rem;
  font-weight: 800;
  color: #fff;
  border-radius: 999px;
  background: var(--ion-color-danger, #c5000f);
}
.pos-kticket__dishes {
  margin: 0;
  padding: 0.35rem 0;
  list-style: none;
}
.pos-kticket__dish {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  padding: 0.3rem 0.7rem;
  font-size: 0.9rem;
}
.pos-kticket__dish-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.pos-kticket__dish--voided .pos-kticket__dish-name {
  text-decoration: line-through;
  opacity: 0.6;
}
.pos-kticket__voided {
  margin-left: auto;
  font-size: 0.72rem;
  font-weight: 800;
  color: var(--ion-color-danger, #c5000f);
  white-space: nowrap;
}
.pos-kticket__actions {
  display: flex;
  justify-content: flex-end;
  padding: 0 0.7rem 0.6rem;
}
.pos-kticket__rush {
  min-height: 2.75rem;
  padding: 0.25rem 1rem;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 800;
  color: var(--ion-color-danger, #c5000f);
  background: transparent;
  border: 1.5px solid var(--ion-color-danger, #c5000f);
  border-radius: 999px;
  cursor: pointer;
}
.pos-kticket__rush--on {
  color: #fff;
  background: var(--ion-color-danger, #c5000f);
}
.pos-kticket__rush:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
