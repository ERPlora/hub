<script setup lang="ts">
// The lines of a manual invoice (INVOICE-F03; the old form's rows): «Description» (the whole row),
// «Qty» (1 to begin with; up to three decimals), «Price» (VAT not included, euros as typed) and «VAT %»
// (21 to begin with); «+ Line» adds one and the cross removes one (never the last). Each line names its
// hooks by its own id (`invoice-line-<uid>-…`), so removing the first never renames the others. What the
// server refused on a line (`lines.<index>.<field>`) is said under its field.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonInput } from '@ionic/vue';

import { blankLine, type DraftLine } from './lines';

withDefaults(
  defineProps<{
    /** What the server refused, by the command's field (`lines.0.quantity`…). */
    fieldErrors?: Readonly<Record<string, string>>;
  }>(),
  { fieldErrors: () => ({}) },
);

const lines = defineModel<DraftLine[]>({ required: true });

type Field = 'description' | 'quantity' | 'price' | 'taxRate';
/** The command's name of each field, for its refusals. */
const SERVER_FIELD: Record<Field, string> = { description: 'description', quantity: 'quantity', price: 'unit_price', taxRate: 'tax_rate' };

function set(uid: number, field: Field, value: unknown): void {
  lines.value = lines.value.map((line) => (line.uid === uid ? { ...line, [field]: String(value ?? '') } : line));
}

function add(): void {
  const next = Math.max(0, ...lines.value.map((line) => line.uid)) + 1;
  lines.value = [...lines.value, blankLine(next)];
}

function remove(uid: number): void {
  if (lines.value.length > 1) lines.value = lines.value.filter((line) => line.uid !== uid);
}

const errorOf = (errors: Readonly<Record<string, string>>, index: number, field: Field): string | undefined =>
  errors[`lines.${index}.${SERVER_FIELD[field]}`];
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
</script>

<template>
  <div
    class="invoice-lines-editor"
    data-testid="invoice-lines-editor"
  >
    <div
      v-for="(line, index) in lines"
      :key="line.uid"
      class="invoice-lines-editor__row"
      :data-testid="`invoice-line-${line.uid}`"
    >
      <ion-input
        class="invoice-lines-editor__description"
        :data-testid="`invoice-line-${line.uid}-description`"
        :label="$t('invoice.create.line.description')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="255"
        :value="line.description"
        :error-text="errorOf(fieldErrors, index, 'description')"
        :class="invalid(errorOf(fieldErrors, index, 'description'))"
        @ion-input="set(line.uid, 'description', $event.detail.value)"
      />
      <ion-input
        :data-testid="`invoice-line-${line.uid}-quantity`"
        :label="$t('invoice.create.line.qty')"
        label-placement="floating"
        fill="outline"
        mode="md"
        inputmode="decimal"
        :value="line.quantity"
        :error-text="errorOf(fieldErrors, index, 'quantity')"
        :class="invalid(errorOf(fieldErrors, index, 'quantity'))"
        @ion-input="set(line.uid, 'quantity', $event.detail.value)"
      />
      <ion-input
        :data-testid="`invoice-line-${line.uid}-price`"
        :label="$t('invoice.create.line.price')"
        label-placement="floating"
        fill="outline"
        mode="md"
        inputmode="decimal"
        :value="line.price"
        :error-text="errorOf(fieldErrors, index, 'price')"
        :class="invalid(errorOf(fieldErrors, index, 'price'))"
        @ion-input="set(line.uid, 'price', $event.detail.value)"
      />
      <ion-input
        :data-testid="`invoice-line-${line.uid}-tax-rate`"
        :label="$t('invoice.create.line.taxPct')"
        label-placement="floating"
        fill="outline"
        mode="md"
        inputmode="decimal"
        :value="line.taxRate"
        :error-text="errorOf(fieldErrors, index, 'taxRate')"
        :class="invalid(errorOf(fieldErrors, index, 'taxRate'))"
        @ion-input="set(line.uid, 'taxRate', $event.detail.value)"
      />
      <ion-button
        v-if="lines.length > 1"
        class="invoice-lines-editor__remove"
        fill="clear"
        color="danger"
        :aria-label="$t('invoice.create.removeLine')"
        :data-testid="`invoice-line-${line.uid}-remove`"
        @click="remove(line.uid)"
      >
        <HubIcon
          slot="icon-only"
          name="ion:close-outline"
        />
      </ion-button>
    </div>
    <ion-button
      class="invoice-lines-editor__add"
      fill="outline"
      data-testid="invoice-lines-add"
      @click="add"
    >
      {{ $t('invoice.create.addLine') }}
    </ion-button>
  </div>
</template>

<style scoped>
.invoice-lines-editor {
  display: grid;
  gap: 12px;
}
/* The description takes the whole row; quantity, price and rate share the next one (the old form, stacked
   in its narrow panel). */
.invoice-lines-editor__row {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr auto;
  gap: 8px;
  align-items: start;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}
.invoice-lines-editor__description {
  grid-column: 1 / -1;
}
.invoice-lines-editor__remove {
  align-self: center;
  min-height: 44px;
}
.invoice-lines-editor__add {
  justify-self: start;
  white-space: nowrap;
}
</style>
