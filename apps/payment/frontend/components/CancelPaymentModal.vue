<script setup lang="ts">
// PAYMENT-F05 «Cancelar un pago»: the «Cancellation reason» of a row's payment, in a form named after it
// (the old screen asked with the browser's prompt), «Cancel payment» in red and «Keep it»; without a
// reason it cannot be pressed. Sends `payment.payment.cancel`; the change comes back through the list's
// stream. A refusal (it finished in the meantime: 409) stays in the form, with the reason typed.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { PaymentOut } from '../operations';

const props = defineProps<{
  /** The payment being cancelled. */
  payment: PaymentOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const cancel = useCommand('payment.payment.cancel');
const reason = ref('');
const title = computed(() => t('payment.payments.cancelForm.title', { reference: props.payment?.reference ?? '' }));

watch(
  () => [open.value, props.payment?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    reason.value = '';
    cancel.error.value = null;
  },
  { immediate: true },
);

async function save(): Promise<void> {
  if (!props.payment) return;
  try {
    await cancel.run({ id: props.payment.id, reason: reason.value.trim() });
  } catch {
    return; // The form paints the error; the reason stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="payment-cancel"
    size="sm"
    role="alertdialog"
    submit-color="danger"
    :title="title"
    :submit-label="$t('payment.payments.cancelForm.submit')"
    :cancel-label="$t('payment.payments.cancelForm.keep')"
    :pending="cancel.pending.value"
    :error="cancel.error.value"
    :submit-disabled="!reason.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <ion-textarea
        data-testid="payment-cancel-reason"
        :value="reason"
        :label="$t('payment.payments.cancelForm.reason')"
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
