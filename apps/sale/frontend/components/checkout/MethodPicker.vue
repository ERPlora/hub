<script setup lang="ts">
// The payment methods of the charge sheet (the old `.pay-methods`): big two-up buttons, icon and name
// (the owner names them, so a mute icon is not enough), the chosen one pressed by border, colour and
// `aria-pressed`. Cash over the legal limit stays visible but unavailable: `aria-disabled`, never the
// native `disabled` (it would swallow the tap), and the tap still reaches the sheet, which says why.
import { HubIcon } from '@erplora/ui/shell';

import { isCash, methodIcon } from '../../lib/checkout/methods';
import type { PaymentMethodOut } from '../../operations';

defineProps<{
  methods: readonly PaymentMethodOut[];
  selectedId: string | undefined;
  /** Over the legal cash limit: cash cannot charge this total. */
  cashOff: boolean;
}>();

const emit = defineEmits<{ pick: [method: PaymentMethodOut] }>();
</script>

<template>
  <div
    class="pay-methods"
    role="group"
    data-testid="sale-checkout-methods"
    :aria-label="$t('sale.checkout.paymentMethod')"
  >
    <button
      v-for="method in methods"
      :key="method.id"
      type="button"
      class="pm-btn"
      :data-testid="`sale-checkout-method-${method.id}`"
      :aria-pressed="method.id === selectedId ? 'true' : 'false'"
      :aria-disabled="cashOff && isCash(method) ? 'true' : undefined"
      :title="cashOff && isCash(method) ? $t('sale.checkout.cashLimitUnavailable') : undefined"
      @click="emit('pick', method)"
    >
      <HubIcon
        :name="methodIcon(method)"
        aria-hidden="true"
      />
      <span class="pm-btn__name">{{ method.display_name }}</span>
    </button>
  </div>
</template>

<style scoped>
.pay-methods {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0.1rem 0 0.55rem;
}

.pm-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  min-height: var(--ep-touch-lg, 56px);
  padding: 0 0.6rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  color: var(--ion-text-color, #1c1b18);
  font: inherit;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
}

.pm-btn ion-icon {
  flex: none;
  font-size: 1.3rem;
}

.pm-btn[aria-pressed='true'] {
  border-color: var(--ion-color-primary, #0091ce);
  color: var(--ion-color-primary, #0091ce);
  box-shadow: var(--ep-ring-accent, inset 0 0 0 1px var(--ion-color-primary, #0091ce));
}

.pm-btn[aria-disabled='true'] {
  opacity: 0.45;
  cursor: not-allowed;
}

.pm-btn:focus-visible {
  outline: 2px solid var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}

.pm-btn__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
