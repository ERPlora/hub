<script setup lang="ts">
// The «Series» of a manual invoice (INVOICE-F03; the old form's select): the active series of the latest
// year that issue invoices (F1) or tickets (F2), as «CODE — name (type)», followed live; the year's
// default one to begin with, else FACT. FACT and TICKET are always offered while the year has not opened
// them (the server opens a factory series on first use, and a new year's from the last one). It says the type of the chosen series
// (`invoiceType`): an invoice needs the whole recipient, a ticket does not. Mounted inside the dialog, so
// the list is only followed while the dialog is open.
import { useLive } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, watch } from 'vue';

import { useT } from '../composables/useT';
import type { InvoiceType } from '../operations';

const code = defineModel<string>({ required: true });
const invoiceType = defineModel<InvoiceType | undefined>('invoiceType');

const t = useT();
const { data } = useLive('invoice.series.list', () => ({ is_active: true, sort: 'year' as const, dir: 'desc' as const, limit: 100, offset: 0 }));

interface Option {
  value: string;
  label: string;
  type: InvoiceType;
  isDefault: boolean;
}

const FALLBACK: readonly { code: string; type: InvoiceType }[] = [
  { code: 'FACT', type: 'F1' },
  { code: 'TICKET', type: 'F2' },
];

const options = computed<Option[]>(() => {
  const rows = data.value?.rows ?? [];
  const latest = Math.max(0, ...rows.map((row) => row.year));
  const ofTheYear = rows.filter((row) => row.year === latest);
  const issuing = ofTheYear.filter((row) => row.invoice_type === 'F1' || row.invoice_type === 'F2');
  // The factory series the year does not have yet are always offered: the server opens them on first use.
  const missing = FALLBACK.filter((item) => !ofTheYear.some((row) => row.code === item.code));
  return [
    ...issuing.map((row) => ({
      value: row.code,
      label: `${row.code} — ${row.display_name || t(`invoice.types.${row.invoice_type}`)} (${row.invoice_type})`,
      type: row.invoice_type,
      isDefault: row.is_default,
    })),
    ...missing.map((item) => ({
      value: item.code,
      label: `${item.code} — ${t(`invoice.typeNames.${item.type}`)}`,
      type: item.type,
      isDefault: false,
    })),
  ];
});

// The first answer (and a list that loses the chosen series) picks the default one, else FACT, else the first.
watch(
  [options, () => data.value],
  () => {
    if (!data.value) return;
    if (options.value.some((option) => option.value === code.value)) return;
    const pick = options.value.find((option) => option.isDefault) ?? options.value.find((option) => option.value === 'FACT') ?? options.value[0];
    if (pick) code.value = pick.value;
  },
  { immediate: true },
);

watch(
  [code, options],
  () => {
    const chosen = options.value.find((option) => option.value === code.value);
    if (chosen && chosen.type !== invoiceType.value) invoiceType.value = chosen.type;
  },
  { immediate: true },
);
</script>

<template>
  <ion-select
    data-testid="invoice-create-series"
    :label="$t('invoice.create.series')"
    label-placement="floating"
    fill="outline"
    mode="md"
    interface="popover"
    :value="code"
    @ion-change="code = String($event.detail.value ?? '')"
  >
    <ion-select-option
      v-for="option in options"
      :key="option.value"
      :value="option.value"
    >
      {{ option.label }}
    </ion-select-option>
  </ion-select>
</template>
