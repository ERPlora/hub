<script setup lang="ts">
// The tender group of the charge sheet (the old `.pay-tender`): how it is paid. «Payments taken» once
// splitting, the methods (only with more than one), then what to type: cash (or any leg of a split)
// types on the keypad, with the change big below; any other method charges the exact amount on the card
// terminal. «Split the payment» opens the split (secondary: most charges are one method); «Add this
// payment» takes each leg (with nothing typed, all that is left). It paints the sheet's tender state
// (useTender) and sends what is tapped.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useLocale } from '../../composables/useT';
import { type Leg, needsTendered, type TenderMethod } from '../../lib/checkout/tender';
import { formatMoney } from '../../lib/format';
import type { PaymentMethodOut } from '../../operations';
import MethodPicker from './MethodPicker.vue';
import PayKeypad from './PayKeypad.vue';
import TenderList from './TenderList.vue';

const props = defineProps<{
  methods: readonly PaymentMethodOut[];
  method: TenderMethod | undefined;
  cashOff: boolean;
  splitting: boolean;
  legs: readonly Leg[];
  /** What the keypad holds, in cents. */
  typed: number;
  change: number;
  /** The server's total of this charge. */
  total: number;
  remaining: number;
}>();

const emit = defineEmits<{
  pick: [method: PaymentMethodOut];
  key: [key: string];
  split: [];
  add: [];
  edit: [id: string];
  remove: [id: string];
}>();

const locale = useLocale();
const money = (cents: number): string => formatMoney(cents, locale.value);

const cash = computed(() => needsTendered(props.method));
const typing = computed(() => cash.value || props.splitting);
const amountLabel = computed(() => (props.splitting && !cash.value ? 'sale.checkout.legAmount' : 'sale.checkout.tendered'));
</script>

<template>
  <div class="checkout-tender">
    <TenderList
      v-if="legs.length"
      :legs="legs"
      @edit="emit('edit', $event)"
      @remove="emit('remove', $event)"
    />
    <MethodPicker
      v-if="methods.length > 1"
      :methods="methods"
      :selected-id="method?.id"
      :cash-off="cashOff"
      @pick="emit('pick', $event)"
    />
    <template v-if="typing">
      <div
        class="amt"
        data-testid="sale-checkout-tendered"
      >
        <span>{{ $t(amountLabel) }}</span>
        <span class="amt__value">{{ money(typed) }}</span>
      </div>
      <div
        v-if="change > 0"
        class="amt amt--change"
        data-testid="sale-checkout-change"
      >
        <span>{{ $t('sale.checkout.change') }}</span>
        <span class="amt__value">{{ money(change) }}</span>
      </div>
      <PayKeypad @key="emit('key', $event)" />
    </template>
    <template v-else>
      <div
        class="amt"
        data-testid="sale-checkout-exact"
      >
        <span>{{ $t('sale.checkout.payExact') }}</span>
        <span class="amt__value">{{ money(total) }}</span>
      </div>
      <p
        class="pay-hint"
        data-testid="sale-checkout-hint"
      >
        {{ $t('sale.checkout.payCardHint', { amount: money(total) }) }}
      </p>
    </template>
    <button
      v-if="total > 0 && !splitting"
      type="button"
      class="pay-split-btn"
      data-testid="sale-checkout-split"
      @click="emit('split')"
    >
      <HubIcon
        name="ion:swap-vertical-outline"
        aria-hidden="true"
      />
      {{ $t('sale.checkout.splitPayment') }}
    </button>
    <button
      v-if="splitting && remaining > 0"
      type="button"
      class="pay-add"
      data-testid="sale-checkout-add-leg"
      @click="emit('add')"
    >
      <HubIcon
        name="ion:add-outline"
        aria-hidden="true"
      />
      {{ $t('sale.checkout.addLeg') }}
    </button>
  </div>
</template>

<style scoped>
.checkout-tender {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

.amt {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  color: var(--ion-text-color, #1c1b18);
  font-size: 1.1rem;
}

.amt__value {
  font-weight: 700;
  white-space: nowrap;
}

/* The change is what the cashier looks for when handing it back. */
.amt--change .amt__value {
  color: var(--ion-color-primary, #0091ce);
  font-size: 1.6rem;
  font-weight: 800;
}

.pay-hint {
  margin: 0.1rem 0 0.4rem;
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.9rem;
}

.pay-split-btn,
.pay-add {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  width: 100%;
  min-height: 52px;
  border-radius: 12px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.pay-split-btn {
  border: 1px solid var(--ion-border-color, #e6e3db);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  color: var(--ion-text-color, #1c1b18);
}

.pay-add {
  border: 1px solid var(--ion-color-primary, #0091ce);
  background: color-mix(in srgb, var(--ion-color-primary, #0091ce) 14%, transparent);
  color: var(--ion-color-primary, #0091ce);
}

.pay-split-btn ion-icon,
.pay-add ion-icon {
  font-size: 1.25rem;
}

.pay-split-btn:focus-visible,
.pay-add:focus-visible {
  outline: 2px solid var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}
</style>
