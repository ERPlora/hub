<script setup lang="ts">
// «Payments taken» of a split payment (the old `.tender-list`): one tall row per leg (a 48 px target)
// with the amount on the right, where the eye compares a column of figures. The row brings the leg back
// to the keypad to be taken again (a text field inside a list is missed with a finger); ✕ removes it.
import { HubIcon } from '@erplora/ui/shell';

import { useLocale, useT } from '../../composables/useT';
import { methodIcon } from '../../lib/checkout/methods';
import type { Leg } from '../../lib/checkout/tender';
import { formatMoney } from '../../lib/format';

defineProps<{ legs: readonly Leg[] }>();

const emit = defineEmits<{ edit: [id: string]; remove: [id: string] }>();

const t = useT();
const locale = useLocale();

const money = (cents: number): string => formatMoney(cents, locale.value);
const named = (leg: Leg) => ({ name: leg.method.display_name, amount: money(leg.amount) });
</script>

<template>
  <div class="tender-list">
    <div
      class="pay-lbl"
      data-testid="sale-checkout-legs-label"
    >
      {{ $t('sale.checkout.paymentsTaken') }}
    </div>
    <ul class="tender-list__rows">
      <li
        v-for="leg in legs"
        :key="leg.id"
        class="tender-row"
        data-testid="sale-checkout-leg"
      >
        <button
          type="button"
          class="tender-edit"
          data-testid="sale-checkout-leg-edit"
          :aria-label="t('sale.checkout.editLeg', named(leg))"
          @click="emit('edit', leg.id)"
        >
          <HubIcon
            :name="methodIcon({ type: leg.method.type, name: leg.method.display_name })"
            aria-hidden="true"
          />
          <span class="tender-name">{{ leg.method.display_name }}</span>
          <span class="tender-amount">{{ money(leg.amount) }}</span>
          <span
            v-if="leg.tendered > leg.amount"
            class="tender-change"
          >
            {{ t('sale.checkout.legChange', { amount: money(leg.tendered - leg.amount) }) }}
          </span>
        </button>
        <button
          type="button"
          class="tender-remove"
          data-testid="sale-checkout-leg-remove"
          :aria-label="t('sale.checkout.removeLeg', named(leg))"
          @click="emit('remove', leg.id)"
        >
          <HubIcon
            name="ion:close-outline"
            aria-hidden="true"
          />
        </button>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.pay-lbl {
  margin: 0 0 0.35rem;
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.tender-list__rows {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin: 0 0 0.2rem;
  padding: 0;
  list-style: none;
}

.tender-row {
  display: flex;
  align-items: stretch;
  gap: 0.35rem;
}

.tender-edit,
.tender-remove {
  min-height: var(--ep-touch-min, 48px);
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: var(--ep-radius-sm, 10px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  font: inherit;
  cursor: pointer;
}

.tender-edit {
  display: flex;
  flex: 1;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
  padding: 0.4rem 0.65rem;
  color: var(--ion-text-color, #1c1b18);
  text-align: left;
}

.tender-edit ion-icon,
.tender-remove ion-icon {
  flex: none;
  font-size: 1.2rem;
  color: var(--ion-color-medium, #8b897f);
}

.tender-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tender-amount {
  font-weight: 800;
  white-space: nowrap;
}

.tender-change {
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.78rem;
  white-space: nowrap;
}

.tender-remove {
  display: flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: var(--ep-touch-min, 48px);
}

.tender-edit:focus-visible,
.tender-remove:focus-visible {
  outline: 2px solid var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}
</style>
