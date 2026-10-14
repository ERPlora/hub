<script setup lang="ts">
// One card per way the sale was paid, in the Refund window (SALE-F31; the old refund «leg»): the
// method, «Charged», «Already refunded» (when something was) and «Refundable» — the server's figures —,
// «Refund amount» to edit what goes back on it (euros as the person types them), and, when the money
// cannot go back its own way, why and «Give it back through» (another method, searched on the server).
// A tender with nothing left only shows its figures.
import { IonInput } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney } from '../../lib/format';
import type { TenderOption } from '../../operations';
import PaymentMethodPicker from './PaymentMethodPicker.vue';

const props = withDefaults(
  defineProps<{
    tender: TenderOption;
    /** Why the amount cannot go as it is (the window's message), painted under it. */
    error?: string;
  }>(),
  { error: undefined },
);

/** What goes back on it, as typed. */
const amount = defineModel<string>('amount', { required: true });
/** The method it goes back through when not its own (its id). */
const destination = defineModel<string>('destination', { required: true });

const t = useT();
const locale = useLocale();

/** The reasons the server gives for a tender that cannot go back its own way; any other reads generic. */
const REASONS = new Set(['already_refunded', 'method_unavailable']);

const money = (cents: number): string => formatMoney(cents, locale.value);

const figures = computed(() =>
  [
    `${t('sale.refund.charged')}: ${money(props.tender.charged)}`,
    props.tender.refunded > 0 ? `${t('sale.refund.refunded')}: ${money(props.tender.refunded)}` : '',
    `${t('sale.refund.remaining')}: ${money(props.tender.remaining)}`,
  ].filter(Boolean),
);

const hasLeft = computed(() => props.tender.remaining > 0);
const why = computed(() => t(`sale.refund.reasons.${REASONS.has(props.tender.reason) ? props.tender.reason : 'not_eligible'}`));
</script>

<template>
  <div
    class="sale-refund-tender"
    :data-testid="`refund-tender-${tender.payment_id}`"
  >
    <div class="sale-refund-tender__head">
      <span
        class="sale-refund-tender__name"
        :data-testid="`refund-tender-name-${tender.payment_id}`"
      >{{ tender.method_name }}</span>
      <ion-input
        v-if="hasLeft"
        class="sale-refund-tender__amount"
        :data-testid="`refund-amount-${tender.payment_id}`"
        :label="$t('sale.refund.amount')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        type="text"
        inputmode="decimal"
        :value="amount"
        :error-text="error"
        :class="{ 'ion-invalid': !!error, 'ion-touched': !!error }"
        @ion-input="amount = String($event.detail.value ?? '')"
      />
    </div>
    <div class="sale-refund-tender__figures">
      <span
        v-for="figure in figures"
        :key="figure"
        data-testid="refund-tender-figure"
      >{{ figure }}</span>
    </div>
    <template v-if="!tender.refundable">
      <p
        class="sale-refund-tender__reason"
        :data-testid="`refund-tender-reason-${tender.payment_id}`"
      >
        {{ why }}
      </p>
      <PaymentMethodPicker
        v-if="hasLeft"
        v-model="destination"
        value-key="id"
        :testid="`refund-destination-${tender.payment_id}`"
        :label="$t('sale.refund.destination')"
      />
    </template>
  </div>
</template>

<style scoped>
.sale-refund-tender {
  display: grid;
  gap: 0.45rem;
  padding: 0.7rem 0.8rem;
  border: 1px solid var(--ion-border-color, #e0ddd4);
  border-radius: 12px;
}
.sale-refund-tender__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.sale-refund-tender__name {
  font-weight: 600;
}
.sale-refund-tender__amount {
  max-width: 11rem;
  text-align: right;
  --padding-end: 0.6rem;
}
.sale-refund-tender__figures {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem 1rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
  font-variant-numeric: tabular-nums;
}
.sale-refund-tender__reason {
  margin: 0;
  color: var(--ion-color-warning-shade, #b07a00);
  font-size: 0.85rem;
}
</style>
