<script setup lang="ts">
// The A4 paper of an invoice (INVOICE-F18), what «Print / PDF» prints: the old `<ok-invoice>` sheet, the
// same layout as the server's `templates/invoice/invoice.html` (the Printing app's and a PDF's). The issuer
// and the document block on top (the title by kind — invoice, simplified invoice, rectifying invoice —,
// «Copy» on a reprint, number, date and, when it differs, the operation date), «Bill to» (a ticket without
// recipient has none), the lines with their price without VAT, their discount apart and their rate, the breakdown with its bases, the totals and the
// note of what it rectifies — in the page's language. Every figure is the server's. With its VeriFactu record
// (VERIFACTU-F19), the record's QR on top, as on the server's paper, with the AEAT's own Spanish words («QR
// tributario:», «VERI*FACTU»; Orden HAC/1177/2024, art. 21).
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDate, formatMoney, formatPercent, formatQuantity, formatUnitPrice } from '../lib/format';
import { documentNote, taxRows } from '../lib/invoice';
import type { InvoiceOut } from '../operations';

const props = withDefaults(
  defineProps<{
    invoice: InvoiceOut;
    /** A reprint: «Copy» under the title. */
    duplicate?: boolean;
    /** VeriFactu's record of the invoice (its QR); none = no QR. */
    record?: { qr_svg: string; qr_url: string } | null;
  }>(),
  { duplicate: false, record: null },
);

const t = useT();
const locale = useLocale();
const money = (cents: number) => formatMoney(cents, locale.value);

const title = computed(() => {
  const type = props.invoice.invoice_type;
  if (type.startsWith('R')) return t('invoice.paper.rectifying');
  return type === 'F2' ? t('invoice.paper.simplified') : t('invoice.paper.invoice');
});
const operationDate = computed(() =>
  props.invoice.operation_date && props.invoice.operation_date !== props.invoice.issue_date
    ? formatDate(props.invoice.operation_date, locale.value)
    : '',
);
const billTo = computed(() => !!(props.invoice.customer_name || props.invoice.customer_tax_id));
// RD 1619/2012 art. 6.1.f: the unit price WITHOUT VAT and, when a line has one, the discount apart; the
// amount is the line's base.
const discounted = computed(() => props.invoice.lines.some((line) => line.discount_amount));
const lines = computed(() =>
  props.invoice.lines.map((line) => ({
    id: line.id,
    description: line.description,
    quantity: formatQuantity(line.quantity, locale.value),
    price: formatUnitPrice(line.unit_price, locale.value),
    discount: line.discount_amount ? money(line.discount_amount) : '',
    rate: formatPercent(line.tax_rate, locale.value),
    amount: money(line.base_amount),
  })),
);
const taxes = computed(() => taxRows(props.invoice.tax_breakdown, t, locale.value));
const note = computed(() => documentNote(props.invoice, t));
</script>

<template>
  <article
    class="invoice-paper"
    data-testid="invoice-paper"
  >
    <div
      v-if="record"
      class="invoice-paper__qr"
      data-testid="invoice-paper-qr"
    >
      <div>QR tributario:</div>
      <img
        :src="record.qr_svg"
        :alt="record.qr_url"
      >
      <div class="invoice-paper__qr-mode">
        VERI*FACTU
      </div>
    </div>
    <div class="invoice-paper__top">
      <div data-testid="invoice-paper-issuer">
        <div class="invoice-paper__issuer-name">
          {{ invoice.issuer_name }}
        </div>
        <div class="invoice-paper__meta">
          <div v-if="invoice.issuer_address">
            {{ invoice.issuer_address }}
          </div>
          <div>{{ $t('invoice.paper.taxId') }}: {{ invoice.issuer_tax_id }}</div>
        </div>
      </div>
      <div class="invoice-paper__doc">
        <div
          class="invoice-paper__title"
          data-testid="invoice-paper-title"
        >
          {{ title }}
        </div>
        <div
          v-if="duplicate"
          class="invoice-paper__copy"
          data-testid="invoice-paper-copy"
        >
          {{ $t('invoice.paper.copy') }}
        </div>
        <div class="invoice-paper__type">
          {{ invoice.invoice_type }}
        </div>
        <div class="invoice-paper__grid">
          <span class="invoice-paper__k">{{ $t('invoice.paper.number') }}</span>
          <span
            class="invoice-paper__v"
            data-testid="invoice-paper-number"
          >{{ invoice.number }}</span>
          <span class="invoice-paper__k">{{ $t('invoice.paper.date') }}</span>
          <span
            class="invoice-paper__v"
            data-testid="invoice-paper-date"
          >{{ formatDate(invoice.issue_date, locale) }}</span>
          <template v-if="operationDate">
            <span class="invoice-paper__k">{{ $t('invoice.paper.operationDate') }}</span>
            <span
              class="invoice-paper__v"
              data-testid="invoice-paper-operation-date"
            >{{ operationDate }}</span>
          </template>
        </div>
      </div>
    </div>
    <div
      v-if="billTo"
      class="invoice-paper__bill-to"
      data-testid="invoice-paper-bill-to"
    >
      <div class="invoice-paper__label">
        {{ $t('invoice.paper.billTo') }}
      </div>
      <div class="invoice-paper__name">
        {{ invoice.customer_name }}
      </div>
      <div class="invoice-paper__meta">
        <div v-if="invoice.customer_address">
          {{ invoice.customer_address }}
        </div>
        <div v-if="invoice.customer_country">
          {{ invoice.customer_country }}
        </div>
        <div v-if="invoice.customer_tax_id">
          {{ $t('invoice.paper.taxId') }}: {{ invoice.customer_tax_id }}
        </div>
      </div>
    </div>
    <table class="invoice-paper__lines">
      <thead>
        <tr>
          <th class="invoice-paper__desc">
            {{ $t('invoice.paper.description') }}
          </th>
          <th class="invoice-paper__num">
            {{ $t('invoice.paper.qty') }}
          </th>
          <th class="invoice-paper__num">
            {{ $t('invoice.paper.price') }}
          </th>
          <th
            v-if="discounted"
            class="invoice-paper__num"
          >
            {{ $t('invoice.paper.discount') }}
          </th>
          <th class="invoice-paper__num">
            {{ $t('invoice.paper.tax') }}
          </th>
          <th class="invoice-paper__num">
            {{ $t('invoice.paper.amount') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="line in lines"
          :key="line.id"
          data-testid="invoice-paper-line"
        >
          <td class="invoice-paper__desc">
            {{ line.description }}
          </td>
          <td class="invoice-paper__num">
            {{ line.quantity }}
          </td>
          <td class="invoice-paper__num">
            {{ line.price }}
          </td>
          <td
            v-if="discounted"
            class="invoice-paper__num"
          >
            {{ line.discount }}
          </td>
          <td class="invoice-paper__num">
            {{ line.rate }}
          </td>
          <td class="invoice-paper__num">
            {{ line.amount }}
          </td>
        </tr>
        <tr v-if="!lines.length">
          <td
            :colspan="discounted ? 6 : 5"
            class="invoice-paper__empty"
          >
            {{ $t('invoice.paper.noLines') }}
          </td>
        </tr>
      </tbody>
    </table>
    <div class="invoice-paper__summary">
      <table data-testid="invoice-paper-taxes">
        <tr>
          <td class="invoice-paper__muted">
            {{ $t('invoice.paper.taxBase') }}
          </td>
          <td class="invoice-paper__num">
            {{ money(invoice.base_amount) }}
          </td>
        </tr>
        <tr
          v-for="(row, index) in taxes"
          :key="index"
        >
          <td class="invoice-paper__muted">
            {{ row.label }} ({{ money(row.base) }})
          </td>
          <td class="invoice-paper__num">
            {{ money(row.amount) }}
          </td>
        </tr>
        <tr class="invoice-paper__grand">
          <td>{{ $t('invoice.paper.total') }}</td>
          <td
            class="invoice-paper__num"
            data-testid="invoice-paper-total"
          >
            {{ money(invoice.total_amount) }}
          </td>
        </tr>
      </table>
    </div>
    <div
      v-if="note"
      class="invoice-paper__legal"
      data-testid="invoice-paper-note"
    >
      {{ note }}
    </div>
  </article>
</template>

<style scoped>
.invoice-paper__qr {
  width: 40mm;
  margin: 0 auto 5mm;
  text-align: center;
  font-size: 9px;
}
.invoice-paper__qr img {
  display: block;
  width: 32mm;
  height: 32mm;
  margin: 1mm auto;
}
.invoice-paper__qr-mode {
  font-weight: 700;
  letter-spacing: 0.06em;
}
.invoice-paper {
  box-sizing: border-box;
  width: 210mm;
  max-width: 100%;
  margin: 0 auto;
  padding: 16mm 14mm;
  background: #fff;
  color: #1c1b18;
  font-family: system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif;
  font-size: 12px;
  line-height: 1.5;
}
.invoice-paper__top {
  display: flex;
  justify-content: space-between;
  gap: 2rem;
  align-items: flex-start;
}
.invoice-paper__issuer-name {
  font-size: 15px;
  font-weight: 700;
}
.invoice-paper__meta {
  color: #6b6b6b;
  font-size: 11px;
}
.invoice-paper__doc {
  text-align: right;
  min-width: 48mm;
}
.invoice-paper__title {
  font-size: 24px;
  font-weight: 800;
  letter-spacing: 0.06em;
  color: #0091ce;
  text-transform: uppercase;
}
.invoice-paper__type,
.invoice-paper__copy {
  font-size: 10px;
  color: #6b6b6b;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.invoice-paper__copy {
  font-weight: 700;
  color: #1c1b18;
}
.invoice-paper__grid {
  margin-top: 0.6rem;
  display: grid;
  grid-template-columns: auto auto;
  gap: 0.1rem 0.8rem;
  justify-content: end;
  font-size: 11px;
}
.invoice-paper__k {
  color: #6b6b6b;
  text-align: right;
}
.invoice-paper__v {
  font-weight: 600;
  text-align: right;
}
.invoice-paper__bill-to {
  margin: 9mm 0 6mm;
  padding: 3mm 4mm;
  background: #ebf6fb;
  border-radius: 8px;
}
.invoice-paper__label {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #6b6b6b;
}
.invoice-paper__name {
  font-weight: 700;
  font-size: 13px;
}
.invoice-paper__lines {
  width: 100%;
  border-collapse: collapse;
  margin-top: 2mm;
}
.invoice-paper__lines thead th {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #6b6b6b;
  text-align: left;
  padding: 2mm;
  border-bottom: 1.5px solid #1c1b18;
}
.invoice-paper__lines tbody td {
  padding: 2mm;
  border-bottom: 1px solid #d9d6cf;
  vertical-align: top;
}
.invoice-paper__lines th.invoice-paper__num,
.invoice-paper__num {
  text-align: right;
  white-space: nowrap;
}
.invoice-paper__desc {
  width: 42%;
}
.invoice-paper__empty {
  text-align: center;
  color: #6b6b6b;
  padding: 6mm;
}
.invoice-paper__summary {
  display: flex;
  justify-content: flex-end;
  margin-top: 4mm;
}
.invoice-paper__summary table {
  border-collapse: collapse;
  min-width: 70mm;
}
.invoice-paper__summary td {
  padding: 1mm 2mm;
}
.invoice-paper__muted {
  color: #6b6b6b;
}
.invoice-paper__grand td {
  font-size: 15px;
  font-weight: 800;
  border-top: 1.5px solid #1c1b18;
  padding-top: 2mm;
}
.invoice-paper__grand .invoice-paper__num {
  color: #0091ce;
}
.invoice-paper__legal {
  margin-top: 8mm;
  padding-top: 3mm;
  border-top: 1px solid #d9d6cf;
  font-size: 9px;
  color: #6b6b6b;
  white-space: pre-line;
  text-align: center;
}
@media print {
  .invoice-paper {
    width: auto;
    max-width: none;
    padding: 0;
  }
  .invoice-paper__bill-to {
    background: transparent;
    border: 1px solid #d9d6cf;
  }
  .invoice-paper__lines thead {
    display: table-header-group;
  }
  .invoice-paper__lines tbody tr,
  .invoice-paper__summary,
  .invoice-paper__legal,
  .invoice-paper__bill-to {
    break-inside: avoid;
  }
}
</style>
