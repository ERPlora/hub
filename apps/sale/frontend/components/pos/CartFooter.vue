<script setup lang="ts">
// The foot of the check: the «Ticket discount» row when the check has one (its percentage and what it
// takes off, as the server's preview says), «Total» — the preview's, a dash while it is on its way —,
// the ticket-discount button (only where discounts are allowed), the printer («Print bill») and
// «Charge · <total>». An empty check can do none of it. When something is missing (a required
// customer), Charge looks blocked and says why, but still takes the tap: the page answers it.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney, formatPercent, useBusinessMoney } from '../../lib/format';

const props = defineProps<{
  hasLines: boolean;
  /** The preview's total; `undefined` while it is on its way. */
  total: number | undefined;
  /** The check's ticket discount: percentage and fixed amount. */
  discountPercent: string;
  discountAmount: number;
  /** What the ticket discount takes off (the preview's `ticket_discount_amount`). */
  ticketDiscount: number;
  allowDiscounts: boolean;
  /** Why Charge cannot go on yet; `null` when it can. */
  blockedReason: string | null;
}>();
const emit = defineEmits<{ discount: []; prebill: []; charge: [] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const hasDiscount = computed(() => Number(props.discountPercent) > 0 || props.discountAmount > 0);
const totalText = computed(() => (props.total === undefined ? '—' : formatMoney(props.total, locale.value, business.value)));
const discountLabel = computed(() => {
  const percent = Number(props.discountPercent) > 0 ? ` −${formatPercent(props.discountPercent, locale.value)}` : '';
  return `${t('sale.pos.discountTicket')}${percent}`;
});
</script>

<template>
  <div class="pos-foot">
    <div
      v-if="hasDiscount"
      class="pos-foot__discount"
      data-testid="pos-ticket-discount-row"
    >
      <span>{{ discountLabel }}</span>
      <span>−{{ formatMoney(ticketDiscount, locale, business) }}</span>
    </div>
    <div class="pos-foot__total">
      <span>{{ $t('sale.pos.total') }}</span>
      <b data-testid="pos-total">{{ totalText }}</b>
    </div>
    <div class="pos-foot__actions">
      <ion-button
        v-if="allowDiscounts"
        fill="outline"
        class="pos-foot__square"
        :class="{ 'pos-foot__square--warning': hasDiscount }"
        data-testid="pos-ticket-discount"
        :disabled="!hasLines"
        :title="$t('sale.pos.discountTicket')"
        :aria-label="$t('sale.pos.discountTicket')"
        @click="emit('discount')"
      >
        <HubIcon
          slot="icon-only"
          name="ion:pricetag-outline"
        />
      </ion-button>
      <ion-button
        fill="outline"
        class="pos-foot__square"
        data-testid="pos-prebill"
        :disabled="!hasLines"
        :title="$t('sale.pos.printPrebill')"
        :aria-label="$t('sale.pos.printPrebill')"
        @click="emit('prebill')"
      >
        <HubIcon
          slot="icon-only"
          name="ion:receipt-outline"
        />
      </ion-button>
      <ion-button
        class="pos-charge"
        :class="{ 'pos-charge--blocked': !!blockedReason }"
        data-testid="pos-charge"
        :disabled="!hasLines"
        :aria-disabled="blockedReason ? 'true' : undefined"
        :title="blockedReason ?? $t('sale.pos.charge')"
        @click="emit('charge')"
      >
        <HubIcon
          slot="start"
          name="ion:card-outline"
        />
        {{ $t('sale.pos.chargeAmount', { amount: totalText }) }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.pos-foot {
  padding: 0.62rem 0.72rem 0.7rem;
  border-top: 1px solid var(--ion-border-color, #e6e3db);
}
.pos-foot__discount {
  display: flex;
  justify-content: space-between;
  margin: 0.1rem 0;
  font-size: 0.9rem;
  color: var(--ion-color-warning-shade, #b7791f);
}
.pos-foot__total {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin: 0.1rem 0 0.65rem;
  font-size: 0.78rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-foot__total b {
  font-size: 1.55rem;
  color: var(--ion-text-color, #1c1b18);
}
.pos-foot__actions {
  display: flex;
  gap: 0.5rem;
}
.pos-foot__square {
  flex: none;
  width: 3.25rem;
  min-height: 3rem;
  margin: 0;
}
.pos-foot__square--warning {
  --color: var(--ion-color-warning-shade, #e0ac08);
  --border-color: var(--ion-color-warning, #ffc409);
}
.pos-charge {
  flex: 1;
  min-height: 3rem;
  margin: 0;
  font-size: 0.98rem;
  font-weight: 700;
  text-transform: none;
}
.pos-charge--blocked {
  --background: var(--ion-color-medium, #92949c);
  --background-activated: var(--ion-color-medium-shade, #808289);
  --background-focused: var(--ion-color-medium-shade, #808289);
  opacity: 0.75;
}
</style>
