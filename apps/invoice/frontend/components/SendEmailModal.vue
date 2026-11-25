<script setup lang="ts">
// «Send by email» (INVOICE-F26): the customer's email, editable, and «Send». A retry goes with the key of the email it
// retries, so nobody gets it twice.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { InvoiceRowOut } from '../operations';
import '../operations/emails';

const props = defineProps<{
  invoice: Pick<InvoiceRowOut, 'id' | 'number'> | null;
  /** The email on the customer's card; empty without one. */
  proposed: string;
}>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const command = useCommand('invoice.email.send');
const to = shallowRef('');
const written = shallowRef(false);
const attempt = shallowRef('');

const newAttempt = (): string => `invoice-email-${globalThis.crypto.randomUUID()}`;

watch(
  open,
  (now) => {
    if (!now) return;
    written.value = false;
    attempt.value = newAttempt();
    command.error.value = null;
  },
  { immediate: true },
);

watch(
  [open, () => props.proposed],
  ([now, proposed]) => {
    if (now && !written.value) to.value = proposed;
  },
  { immediate: true },
);

const address = computed(() => to.value.trim());
const error = computed(() => refusal(command.error.value, t('invoice.email.failed')));

function write(value: unknown): void {
  written.value = true;
  to.value = String(value ?? '');
}

async function send(): Promise<void> {
  if (!props.invoice || !address.value) return;
  try {
    await command.run({ invoice_id: props.invoice.id, to: address.value, attempt_key: attempt.value });
  } catch {
    return; // The window shows `command.error`.
  }
  toastSuccess(t('invoice.email.onItsWay', { to: address.value }));
  open.value = false;
}

const canDismiss = useUnsavedFormOnOpen('invoice-email', to, open);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    testid="invoice-email"
    :title="$t('invoice.email.title')"
    :submit-label="$t('invoice.email.submit')"
    :cancel-label="$t('invoice.cancel')"
    :pending="command.pending.value"
    :error="error"
    :submit-disabled="!address"
    @submit="send"
  >
    <template #default="{ fieldErrors }">
      <ion-input
        data-testid="invoice-email-to"
        name="to"
        type="email"
        inputmode="email"
        autocomplete="off"
        :label="$t('invoice.email.to')"
        :helper-text="$t('invoice.email.help', { number: invoice?.number ?? '' })"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="254"
        :value="to"
        :error-text="fieldErrors.to"
        :class="{ 'ion-invalid': !!fieldErrors.to, 'ion-touched': !!fieldErrors.to }"
        @ion-input="write($event.detail.value)"
      />
    </template>
  </FormModal>
</template>
