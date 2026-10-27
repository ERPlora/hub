<script setup lang="ts">
// The discount sheet (SALE-F14): «Ticket discount» or «Discount on <item>». A percentage on the keypad
// (never over 100); the ticket can switch to a fixed amount with the button of the business's currency (switching clears
// what was typed; a check with only a fixed amount opens on it). «Apply −N %» / «Apply −<amount>»
// hands one kind up (the other at 0); «Remove» hands both at 0. The page picks the door — the
// manager's above the business's cap — and a refusal is read here, over the buttons.
import { IonButton, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { centsFromAmount, currencySign, formatMoney, formatPercent, moneyDecimals, useBusinessMoney } from '../../lib/format';
import PosNumpad from './PosNumpad.vue';
import PosSheet from './PosSheet.vue';

export type DiscountMode = 'percent' | 'amount';

const props = defineProps<{
  /** The line's name; `null` for the ticket. */
  name: string | null;
  /** The ticket's fixed discount now, in cents (it decides the mode it opens in). */
  amount: number;
  pending: boolean;
  error: string | null;
}>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ apply: [discount: { percent: string; amount: number }] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const mode = shallowRef<DiscountMode>('percent');
const typed = shallowRef('');
const ticket = computed(() => props.name === null);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    typed.value = '';
    mode.value = ticket.value && props.amount > 0 ? 'amount' : 'percent';
  },
  { immediate: true },
);

watch(typed, (now, before) => {
  if (mode.value === 'percent' && Number(now) > 100) typed.value = before;
});

const value = computed(() => typed.value.replace(/\.$/, '') || '0');
const cents = computed(() => centsFromAmount(value.value, business.value) ?? 0);
const shown = computed(() => (mode.value === 'percent' ? formatPercent(value.value, locale.value) : formatMoney(cents.value, locale.value, business.value)));
/** The amount button's sign: the business's currency («€», «zł»; gh:sales#380), «¤» until the business answers. */
const currency = computed(() => currencySign(locale.value, business.value) || '¤');
const ready = computed(() => (mode.value === 'percent' ? Number(value.value) > 0 : cents.value > 0));
const title = computed(() => (ticket.value ? t('sale.pos.discountTicket') : t('sale.pos.discountLineOf', { name: props.name })));

function onMode(event: CustomEvent<{ value?: string | number }>): void {
  mode.value = event.detail.value === 'amount' ? 'amount' : 'percent';
  typed.value = '';
}

function apply(): void {
  if (!ready.value) return;
  emit('apply', mode.value === 'percent' ? { percent: value.value, amount: 0 } : { percent: '0', amount: cents.value });
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="title"
    testid="pos-discount"
  >
    <template #top>
      <ion-segment
        v-if="ticket"
        class="pos-discount__mode"
        data-testid="pos-discount-mode"
        :value="mode"
        :aria-label="$t('sale.pos.discountMode')"
        @ion-change="onMode"
      >
        <ion-segment-button value="percent">
          <ion-label>%</ion-label>
        </ion-segment-button>
        <ion-segment-button value="amount">
          <ion-label>{{ currency }}</ion-label>
        </ion-segment-button>
      </ion-segment>
      <p
        class="pos-sheet-figure"
        data-testid="pos-discount-value"
      >
        {{ shown }}
      </p>
    </template>
    <PosNumpad
      v-model="typed"
      :decimals="mode === 'percent' ? 2 : moneyDecimals(business)"
      :max-length="mode === 'percent' ? 6 : 9"
    />
    <template #foot>
      <div class="pos-sheet-foot">
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-discount-error"
        >
          {{ error }}
        </p>
        <div class="pos-sheet-actions">
          <ion-button
            fill="outline"
            color="medium"
            data-testid="pos-discount-remove"
            :disabled="pending"
            @click="emit('apply', { percent: '0', amount: 0 })"
          >
            {{ $t('sale.pos.discountRemove') }}
          </ion-button>
          <ion-button
            class="pos-sheet-confirm"
            data-testid="pos-discount-apply"
            :disabled="!ready || pending"
            @click="apply"
          >
            {{ ready ? $t('sale.pos.discountApplyValue', { value: shown }) : $t('sale.pos.discountApply') }}
          </ion-button>
        </div>
      </div>
    </template>
  </PosSheet>
</template>

<style scoped>
.pos-discount__mode {
  max-width: 12rem;
  margin: 0 auto 0.4rem;
}
</style>
