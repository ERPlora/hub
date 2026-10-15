<script setup lang="ts">
// «New manual invoice» (INVOICE-F03; the old create panel of the table, now a dialog): the «Series» (the
// active invoice and ticket series), the recipient (a card of Customers or typed: name, country, tax ID,
// address), «Notes» and the lines (description, quantity, price WITHOUT VAT, VAT %). «Issue invoice» stays
// grey until every line has a description, a quantity and a price and, for an invoice series (F1), until
// the recipient is complete; a price that is not an amount is said with its line before anything is sent.
// It runs `invoice.invoice.create` (the server computes the VAT, closed once per rate, and numbers it),
// says «Invoice <number> issued» and closes; the list paints the new row by itself, live. A refusal stays in
// the window, under its field when it is one (recipient or line), and what was written is kept.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { type Recipient, recipientComplete, recipientFrom, recipientPayload } from '../lib/recipient';
import { refusal } from '../lib/refusal';
import type { InvoiceOut, InvoiceType } from '../operations';
import InvoiceLinesEditor from './InvoiceLinesEditor.vue';
import { blankLine, type DraftLine, linePayload, linesReady, unreadablePrice } from './lines';
import RecipientFields from './RecipientFields.vue';
import SeriesSelect from './SeriesSelect.vue';

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ created: [invoice: InvoiceOut] }>();

const t = useT();
const command = useCommand('invoice.invoice.create');
const seriesCode = shallowRef('');
const invoiceType = shallowRef<InvoiceType | undefined>(undefined);
const recipient = shallowRef<Recipient>(recipientFrom(null));
const notes = shallowRef('');
const lines = shallowRef<DraftLine[]>([blankLine(1)]);
/** The form's own refusal (a price that is not an amount), before anything is sent. */
const local = shallowRef<string | null>(null);

watch(
  open,
  (now) => {
    if (!now) return;
    recipient.value = recipientFrom(null);
    notes.value = '';
    lines.value = [blankLine(1)];
    local.value = null;
    command.error.value = null;
  },
  { immediate: true },
);

/** An invoice (F1) names its recipient whole; a ticket (F2) may name nobody. */
const needsRecipient = computed(() => invoiceType.value !== 'F2');
const ready = computed(() => linesReady(lines.value) && (!needsRecipient.value || recipientComplete(recipient.value)));
const error = computed<FormModalError | null>(() =>
  local.value ? { message: local.value } : refusal(command.error.value, t('invoice.create.failed')),
);
const fieldErrors = computed(() => error.value?.fields ?? {});

async function issue(): Promise<void> {
  if (!ready.value || command.pending.value) return;
  const unreadable = unreadablePrice(lines.value);
  local.value = unreadable === null ? null : t('invoice.create.notAnAmount', { line: unreadable });
  if (local.value) return;
  let invoice;
  try {
    invoice = await command.run({
      ...(seriesCode.value ? { series_code: seriesCode.value } : {}),
      ...recipientPayload(recipient.value),
      notes: notes.value.trim(),
      lines: lines.value.map(linePayload),
    });
  } catch {
    return; // The window shows `command.error`.
  }
  void toastSuccess(t('invoice.create.done', { number: invoice.number }));
  open.value = false;
  emit('created', invoice);
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="invoice-create"
    :title="$t('invoice.create.title')"
    :submit-label="$t('invoice.create.submit')"
    :cancel-label="$t('invoice.cancel')"
    :pending="command.pending.value"
    :error="error"
    :submit-disabled="!ready"
    @submit="issue"
  >
    <div class="invoice-create__fields">
      <SeriesSelect
        v-model="seriesCode"
        v-model:invoice-type="invoiceType"
      />
      <RecipientFields
        v-model="recipient"
        :field-errors="fieldErrors"
      />
      <ion-input
        data-testid="invoice-create-notes"
        :label="$t('invoice.create.notes')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="2000"
        :value="notes"
        :error-text="fieldErrors.notes"
        @ion-input="notes = String($event.detail.value ?? '')"
      />
      <InvoiceLinesEditor
        v-model="lines"
        :field-errors="fieldErrors"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.invoice-create__fields {
  display: grid;
  gap: 14px;
}
</style>
