<script setup lang="ts">
// «New manual invoice» (INVOICE-F03; the old create panel of the table, now a dialog): the «Series» (the
// active invoice and ticket series), the recipient (a card of Customers or typed: name, country, tax ID,
// address), «Notes» and the lines (description, quantity, price WITHOUT the tax, rate %). The rate is named by
// the tax of the business's territory, as Taxes publishes it (`useTaxKind`, `tax.settings.get`), and starts at
// its general rate (`invoice.invoice.line_defaults`); both followed live (TAX-F11): «VAT %» and 21 on the
// peninsula, «IGIC %» in the Canary Islands, «IPSI %» in Ceuta and Melilla, blank when the territory has no
// rule of its own tax; a plain «Tax %» while the territory's tax is not known. «Issue invoice» stays grey until every
// line has a description, a quantity, a price and a rate and, for an invoice series (F1), until the
// recipient is complete; a price that is not an amount is said with its line before anything is sent.
// It runs `invoice.invoice.create` (the server computes the tax, closed once per rate, and numbers it),
// says «Invoice <number> issued» and closes; the list paints the new row by itself, live. A refusal stays in
// the window, under its field when it is one (recipient or line), and what was written is kept.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useTaxKind } from '../../../tax/frontend/composables/useTaxName';
import { useLocale, useT } from '../composables/useT';
import { typedRate, useBusinessMoney } from '../lib/format';
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
const locale = useLocale();
const command = useCommand('invoice.invoice.create');
/** The tax a typed rate is declared with (the business territory's, from Taxes) and its general rate. */
const tax = useTaxKind();
const defaults = useLive('invoice.invoice.line_defaults', () => ({}));
const defaultRate = computed(() => typedRate(defaults.data.value?.tax_rate ?? null, locale.value));
/** The business's money: each price is read in it (its symbol is no part of it; its own decimals). */
const money = useBusinessMoney();
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
    lines.value = [blankLine(1, defaultRate.value)];
    local.value = null;
    command.error.value = null;
  },
  { immediate: true },
);

// A line still at the rate it started with follows the territory's answer (it may come after the window
// opens, or change while it is open); a rate the person typed stays.
watch(defaultRate, (now, before) => {
  lines.value = lines.value.map((line) => (line.taxRate === before ? { ...line, taxRate: now } : line));
});

/** An invoice (F1) names its recipient whole; a ticket (F2) may name nobody. */
const needsRecipient = computed(() => invoiceType.value !== 'F2');
const ready = computed(() => linesReady(lines.value) && (!needsRecipient.value || recipientComplete(recipient.value)));
const error = computed<FormModalError | null>(() => {
  if (local.value) return { message: local.value };
  // Without the territory's general rate the line starts blank: the person types it.
  const unknownTerritory = defaults.error.value ? { message: t('invoice.create.defaultsFailed') } : null;
  return refusal(command.error.value, t('invoice.create.failed')) ?? unknownTerritory;
});
const fieldErrors = computed(() => error.value?.fields ?? {});

async function issue(): Promise<void> {
  if (!ready.value || command.pending.value) return;
  const unreadable = unreadablePrice(lines.value, money.value);
  local.value = unreadable === null ? null : t('invoice.create.notAnAmount', { line: unreadable });
  if (local.value) return;
  let invoice;
  try {
    invoice = await command.run({
      ...(seriesCode.value ? { series_code: seriesCode.value } : {}),
      ...recipientPayload(recipient.value),
      notes: notes.value.trim(),
      lines: lines.value.map((line) => linePayload(line, money.value)),
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
        :tax="tax"
        :default-rate="defaultRate"
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
