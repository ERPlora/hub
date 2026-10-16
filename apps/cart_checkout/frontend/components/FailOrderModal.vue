<script setup lang="ts">
// CART_CHECKOUT-F10 «Registrar que el pago falló»: the «Reason» of a row's order, in a form named after it
// (the old screen sent «Cancelled by operator» without asking), «Fail order» in red and «Keep it»;
// without a reason it cannot be pressed. Sends `cart_checkout.order.fail`; the change comes back through
// the list's stream. A refusal (it was completed in the meantime: 409) stays in the form, with the reason.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { OrderOut } from '../operations';

const props = defineProps<{
  /** The order that failed. */
  order: OrderOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const fail = useCommand('cart_checkout.order.fail');
const reason = ref('');
const title = computed(() => t('cart_checkout.orders.failForm.title', { number: props.order?.order_number ?? '' }));

watch(
  () => [open.value, props.order?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    reason.value = '';
    fail.error.value = null;
  },
  { immediate: true },
);

async function save(): Promise<void> {
  if (!props.order) return;
  try {
    await fail.run({ order_id: props.order.id, reason: reason.value.trim() });
  } catch {
    return; // The form paints the error; the reason stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="cart-checkout-fail"
    size="sm"
    role="alertdialog"
    submit-color="danger"
    :title="title"
    :submit-label="$t('cart_checkout.orders.failForm.submit')"
    :cancel-label="$t('cart_checkout.orders.failForm.keep')"
    :pending="fail.pending.value"
    :error="fail.error.value"
    :submit-disabled="!reason.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <ion-textarea
        data-testid="cart-checkout-fail-reason"
        :value="reason"
        :label="$t('cart_checkout.orders.failForm.reason')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :auto-grow="true"
        :maxlength="500"
        data-autofocus
        :error-text="fieldErrors.reason"
        :class="{ 'ion-invalid': !!fieldErrors.reason, 'ion-touched': !!fieldErrors.reason }"
        @ion-input="reason = $event.detail.value ?? ''"
      />
    </template>
  </FormModal>
</template>
