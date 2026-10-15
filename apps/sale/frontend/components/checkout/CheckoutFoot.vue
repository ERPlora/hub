<script setup lang="ts">
// The foot of the charge sheet (the old `.sheet-foot`): what went wrong, why it cannot charge yet, and
// ONE button that says what it does and for how much. Blocked, it stays tappable (`aria-disabled`, never
// `disabled`: that would swallow the tap) and answers with the reason (`blocked`); only «Charging…» and
// a total still loading use the native `disabled`. A refusal is the server's own words; a lost answer is
// said as such, and when nobody knows whether it charged, «Check in Sales» goes and looks. Cash with the
// drawer closed (SALE-F08) offers «Open a cash session» to whoever may open one.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import type { CheckoutFailure } from '../../composables/checkout/useCheckout';
import { useLocale, useT } from '../../composables/useT';
import type { ChargeBlock } from '../../lib/checkout/blocks';
import { needsTendered, type TenderMethod } from '../../lib/checkout/tender';
import { formatMoney } from '../../lib/format';

const props = defineProps<{
  /** The server's total of this charge; `undefined` while it loads. */
  total: number | undefined;
  method: TenderMethod | undefined;
  /** Paid in several legs: the button names no method. */
  split: boolean;
  block: ChargeBlock | null;
  busy: boolean;
  /** The total and the methods are there (nothing loading or failed). */
  ready: boolean;
  failure: CheckoutFailure | null;
  /** Cash register is on and this person may open a cash session (absent = no). */
  canOpenDrawer?: boolean;
}>();

const emit = defineEmits<{
  confirm: [];
  /** A tap on the blocked button, with what to say. */
  blocked: [block: ChargeBlock, message: string];
  checkSales: [];
  /** «Open a cash session»: the cash register's sessions, to open one. */
  openDrawer: [];
}>();

/** Cash refused with the drawer closed, and somebody here who may open it. */
const drawerClosed = computed(
  () => props.canOpenDrawer && props.failure?.kind === 'refused' && props.failure.code === 'sale.cash_register_closed',
);

const t = useT();
const locale = useLocale();
const money = (cents: number): string => formatMoney(cents, locale.value);

/** The short form, on the button; none keeps «Charge <amount>». */
const short = computed(() => {
  const block = props.block;
  if (!block || block.kind === 'tenderedMissing') return '';
  if (block.kind === 'remaining') return t('sale.checkout.block.remaining', { amount: money(block.amount) });
  return t(`sale.checkout.block.${block.kind}`);
});

/** The whole reason, written above the button; the recipient's is the details box itself. */
const reason = computed(() => {
  const block = props.block;
  // The recipient's box itself says what is missing or wrong.
  if (!block || block.kind === 'recipient' || block.kind === 'taxIdInvalid' || block.kind === 'idTypeRequired') return '';
  if (block.kind === 'cashLimit') return t('sale.checkout.cashLimitReason', { amount: money(block.limit) });
  if (block.kind === 'remaining') return t('sale.checkout.reason.remaining', { amount: money(block.amount) });
  return t(`sale.checkout.reason.${block.kind}`);
});

const label = computed(() => {
  if (props.busy) return t('sale.checkout.charging');
  if (short.value) return short.value;
  if (props.total === undefined) return t('sale.checkout.title');
  const amount = money(props.total);
  if (props.split || needsTendered(props.method) || !props.method) return t('sale.checkout.charge', { amount });
  if (props.method.type === 'card') return t('sale.checkout.chargeWithCard', { amount });
  return t('sale.checkout.chargeWith', { amount, method: props.method.display_name });
});

const failureText = computed(() => {
  const failure = props.failure;
  if (!failure) return '';
  if (failure.kind === 'refused') return failure.message;
  return t(failure.kind === 'unknown' ? 'sale.checkout.checkoutUnknown' : 'sale.checkout.serverUnavailable');
});

function press(): void {
  if (props.busy || !props.ready) return;
  if (props.block) {
    emit('blocked', props.block, reason.value || short.value);
    return;
  }
  emit('confirm');
}
</script>

<template>
  <div class="sheet-foot">
    <template v-if="failure">
      <p
        class="pay-err"
        role="alert"
        data-testid="sale-checkout-error"
      >
        {{ failureText }}
      </p>
      <ion-button
        v-if="failure.kind === 'unknown'"
        class="pay-check-sales"
        fill="outline"
        size="small"
        data-testid="sale-checkout-check-sales"
        @click="emit('checkSales')"
      >
        <HubIcon
          slot="start"
          name="ion:cart-outline"
          aria-hidden="true"
        />
        {{ $t('sale.checkout.checkSales') }}
      </ion-button>
      <ion-button
        v-if="drawerClosed"
        class="pay-check-sales"
        fill="outline"
        size="small"
        data-testid="sale-checkout-open-drawer"
        @click="emit('openDrawer')"
      >
        <HubIcon
          slot="start"
          name="ion:cash-outline"
          aria-hidden="true"
        />
        {{ $t('sale.checkout.openDrawer') }}
      </ion-button>
    </template>
    <p
      v-if="reason"
      class="pay-block-reason"
      data-testid="sale-checkout-block-reason"
    >
      {{ reason }}
    </p>
    <ion-button
      class="charge"
      expand="block"
      data-testid="sale-checkout-confirm"
      :disabled="busy || !ready"
      :aria-disabled="block ? 'true' : undefined"
      :data-blocked="block ? 'true' : undefined"
      @click="press"
    >
      <ion-spinner
        v-if="busy"
        slot="start"
        name="crescent"
        aria-hidden="true"
      />
      {{ label }}
    </ion-button>
  </div>
</template>

<style scoped>
.pay-err {
  margin: 0.4rem 0 0.5rem;
  color: var(--ion-color-danger, #d9480f);
}

.pay-check-sales {
  margin: 0 0 0.6rem;
}

.pay-block-reason {
  margin: 0 0 0.45rem;
  padding: 0.5rem 0.65rem;
  border: 1px solid var(--ion-color-warning, #e8a33d);
  border-radius: 0.6rem;
  background: color-mix(in srgb, var(--ion-color-warning, #e8a33d) 12%, transparent);
  color: var(--ion-text-color, #1c1b18);
  font-size: 0.9rem;
}

.charge {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 700;
}

/* A full-colour button that is not going to charge is a promise the screen does not keep: dimmed, and
   still live to the tap. */
.charge[data-blocked] {
  --background: var(--ion-color-medium, #92949c);
  --background-activated: var(--ion-color-medium-shade, #808289);
  --background-focused: var(--ion-color-medium-shade, #808289);
  opacity: 0.75;
}
</style>
