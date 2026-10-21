<script setup lang="ts">
// A ticket's detail (WORKBOOK «Pantallas · Comandas»): tapping a row opens it, live (`kitchen.ticket.get`):
// destination, type, status, waiter and when it was sent, its notes, and its dishes with their quantity,
// their menu and options (KITCHEN-F06, F07), station and state (a voided one with its reason). The page
// mounts it only while it is open.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDateTime, formatQuantity } from '../lib/format';

const props = defineProps<{ ticketId: string; timezone: string }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const NONE = '—';

const { data: ticket, status, error } = useLive('kitchen.ticket.get', () => ({ ticket_id: props.ticketId }));

const rows = computed(() => {
  const current = ticket.value;
  if (!current) return [];
  return [
    ['label', t('kitchen.tickets.columns.label'), current.label || NONE],
    ['type', t('kitchen.tickets.columns.type'), t(`kitchen.orderType.${current.order_type}`)],
    ['priority', t('kitchen.tickets.columns.priority'), t(`kitchen.priority.${current.priority}`)],
    ['status', t('kitchen.tickets.columns.status'), t(`kitchen.status.${current.status}`)],
    ['waiter', t('kitchen.history.columns.who'), current.waiter || NONE],
    ['received', t('kitchen.tickets.columns.received'), formatDateTime(current.received_at, locale.value, props.timezone)],
    ['notes', t('kitchen.detail.notes'), current.notes || NONE],
  ] as const;
});
const title = computed(() => t('kitchen.detail.title', { number: ticket.value?.number ?? '' }));
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="kitchen-ticket-detail"
    :title="title"
  >
    <InlineFeedback
      v-if="status === 'error' && error"
      tone="danger"
      data-testid="kitchen-ticket-detail-error"
      :heading="t('kitchen.detail.loadError')"
    >
      {{ error.message }}
    </InlineFeedback>
    <div
      v-else
      data-testid="kitchen-ticket-detail-body"
    >
      <dl class="kitchen-detail">
        <template
          v-for="[key, label, value] in rows"
          :key="key"
        >
          <dt>{{ label }}</dt>
          <dd :data-testid="`kitchen-ticket-detail-${key}`">
            {{ value }}
          </dd>
        </template>
      </dl>
      <h3 class="kitchen-detail__title">
        {{ t('kitchen.detail.dishes') }}
      </h3>
      <ul class="kitchen-detail__dishes">
        <li
          v-for="dish in ticket?.items ?? []"
          :key="dish.id"
          :data-status="dish.status"
        >
          <strong>{{ formatQuantity(dish.quantity, locale) }}× {{ dish.name }}</strong>
          <span
            v-if="dish.menu_name"
            :data-testid="`kitchen-ticket-detail-dish-${dish.id}-menu`"
          >{{ dish.menu_name }}</span>
          <span
            v-if="dish.modifiers.length"
            :data-testid="`kitchen-ticket-detail-dish-${dish.id}-modifiers`"
          >{{ dish.modifiers.join(', ') }}</span>
          <span>{{ dish.station_name || t('kitchen.display.stationNone') }}</span>
          <span>{{ t(`kitchen.itemStatus.${dish.status}`) }}</span>
          <em v-if="dish.void_reason">{{ dish.void_reason }}</em>
          <em v-else-if="dish.notes">{{ dish.notes }}</em>
        </li>
      </ul>
    </div>
    <template #footer="{ cancel }">
      <ion-button
        fill="clear"
        data-testid="kitchen-ticket-detail-done"
        @click="cancel"
      >
        {{ t('kitchen.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.kitchen-detail {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.4rem 1rem;
  margin: 0;
}
.kitchen-detail dt {
  color: var(--ion-color-medium, #8b897f);
}
.kitchen-detail dd {
  margin: 0;
  white-space: pre-wrap;
}
.kitchen-detail__title {
  margin: 1rem 0 0.4rem;
  font-size: 1rem;
}
.kitchen-detail__dishes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.4rem;
}
.kitchen-detail__dishes li {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 0.75rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}
.kitchen-detail__dishes li[data-status='voided'] strong,
.kitchen-detail__dishes li[data-status='cancelled'] strong {
  text-decoration: line-through;
}
</style>
