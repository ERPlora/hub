<script setup lang="ts">
// «Full invoice» of a ticket (INVOICE-F05: the customer comes back with their ticket and asks for the invoice
// in their name): «Full invoice of ticket <number>», what will happen (the ticket stays; an F3 with the same
// figures replaces it), the recipient (a card of Customers, or typed) and «Issue full invoice», grey until
// name, tax ID and address are there. It runs `invoice.invoice.substitute` by the ticket's id, says so,
// closes and hands the new F3 to the page. A refusal is read inside the window; one of a field, under it.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { type Recipient, recipientComplete, recipientFrom, recipientPayload } from '../lib/recipient';
import { refusal } from '../lib/refusal';
import type { InvoiceOut, InvoiceRowOut } from '../operations';
import RecipientFields from './RecipientFields.vue';

const props = defineProps<{ ticket: Pick<InvoiceRowOut, 'id' | 'number'> | null }>();

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ substituted: [invoice: InvoiceOut] }>();

const t = useT();
const command = useCommand('invoice.invoice.substitute');
const recipient = shallowRef<Recipient>(recipientFrom(null));

watch(
  open,
  (now) => {
    if (!now) return;
    recipient.value = recipientFrom(null);
    command.error.value = null;
  },
  { immediate: true },
);

const error = computed(() => refusal(command.error.value, t('invoice.substitute.failed')));
const fieldErrors = computed(() => error.value?.fields ?? {});

async function issue(): Promise<void> {
  const ticket = props.ticket;
  if (!ticket || !recipientComplete(recipient.value)) return;
  let answer;
  try {
    answer = await command.run({ invoice_id: ticket.id, ...recipientPayload(recipient.value) });
  } catch {
    return; // The window shows `command.error`.
  }
  if (!answer.invoice) return;
  void toastSuccess(t('invoice.substitute.done', { number: answer.invoice.number }));
  open.value = false;
  emit('substituted', answer.invoice);
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="invoice-substitute"
    :title="$t('invoice.substitute.title', { number: ticket?.number ?? '' })"
    :submit-label="$t('invoice.substitute.submit')"
    :cancel-label="$t('invoice.cancel')"
    :pending="command.pending.value"
    :error="error"
    :submit-disabled="!recipientComplete(recipient)"
    @submit="issue"
  >
    <p
      class="invoice-substitute__intro"
      data-testid="invoice-substitute-intro"
    >
      {{ $t('invoice.substitute.intro') }}
    </p>
    <RecipientFields
      v-model="recipient"
      :field-errors="fieldErrors"
    />
  </FormModal>
</template>

<style scoped>
.invoice-substitute__intro {
  margin: 0 0 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.9rem;
}
</style>
