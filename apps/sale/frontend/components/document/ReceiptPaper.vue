<script setup lang="ts">
// The ticket of a sale as it prints (SALE-F29; the old `ok-receipt`, thermal paper 80 mm): the header
// from the receipt settings (first line = the name, else «My business»; the rest = the address),
// «DUPLICATE» on a reprint, the number with the date and time, the customer, the lines («qty × unit
// price», a gift «(On the house)», the note), «Subtotal», a VAT row per rate from the sale's breakdown,
// «TOTAL», the payment rows and «Change», the discount already applied and the footer. Every figure is
// the server's; this only lays them out. No fiscal QR yet: the invoice number and the VeriFactu QR
// arrive with Invoicing and VeriFactu. `printPaper` prints a copy of this very element.
import { formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney, formatPercent, formatQuantity } from '../../lib/format';
import type { SaleOut, SettingsOut } from '../../operations';

const props = withDefaults(
  defineProps<{
    sale: SaleOut;
    /** The receipt settings (`sale.pos_settings.get`); none = the default header and no footer. */
    settings?: Pick<SettingsOut, 'receipt_header' | 'receipt_footer'> | null;
    /** A reprint: «DUPLICATE» on top. */
    duplicate?: boolean;
  }>(),
  { settings: null, duplicate: false },
);

const t = useT();
const locale = useLocale();

/** The taxes the paper names short («IVA 10 %»); any other keeps the label its rule gave it. */
const TAX_NAMES = new Set(['vat', 'surcharge', 'igic', 'ipsi']);

const money = (cents: number): string => formatMoney(cents, locale.value);

const header = computed(() => (props.settings?.receipt_header ?? '').split('\n').map((line) => line.trim()).filter(Boolean));
const businessName = computed(() => header.value[0] ?? t('sale.document.defaultBusiness'));
const address = computed(() => header.value.slice(1));
const when = computed(() => formatDateTime(props.sale.created_at, locale.value));

const lines = computed(() =>
  props.sale.lines.map((line) => ({
    id: line.id,
    name: line.is_gift ? `${line.name} ${t('sale.document.gift')}` : line.name,
    detail: `${formatQuantity(line.quantity, line.unit, locale.value)} × ${money(line.unit_price)}`,
    note: line.notes.trim(),
    amount: money(line.line_total),
  })),
);

const taxes = computed(() =>
  props.sale.breakdown.map((row) => ({
    key: `${row.label}|${row.rate_pct}`,
    label: `${TAX_NAMES.has(row.label) ? t(`sale.document.taxes.${row.label}`) : row.label} ${formatPercent(row.rate_pct, locale.value)}`,
    amount: money(row.tax),
  })),
);

const payments = computed(() =>
  [...props.sale.payments]
    .sort((a, b) => a.position - b.position)
    .map((payment) => ({ id: payment.id, method: payment.method_name, amount: money(payment.tendered || payment.amount) })),
);
/** Change is given in cash: a cash tender always says it, 0 included. */
const showsChange = computed(() => props.sale.payments.some((payment) => payment.method_type === 'cash'));

const footer = computed(() =>
  [
    props.sale.discount_amount > 0 ? t('sale.document.discountApplied', { amount: money(props.sale.discount_amount) }) : '',
    (props.settings?.receipt_footer ?? '').trim(),
  ].filter(Boolean),
);
</script>

<template>
  <article
    class="sale-receipt"
    data-testid="sale-receipt"
  >
    <div
      v-if="duplicate"
      class="sale-receipt__duplicate"
      data-testid="sale-receipt-duplicate"
    >
      {{ $t('sale.document.duplicate') }}
    </div>
    <header class="sale-receipt__center">
      <div
        class="sale-receipt__name"
        data-testid="sale-receipt-name"
      >
        {{ businessName }}
      </div>
      <div
        v-for="(text, index) in address"
        :key="index"
        class="sale-receipt__small"
        data-testid="sale-receipt-address"
      >
        {{ text }}
      </div>
    </header>
    <hr class="sale-receipt__rule">
    <div class="sale-receipt__meta">
      <span data-testid="sale-receipt-number">{{ $t('sale.document.receipt') }}: <strong>{{ sale.number }}</strong></span>
      <span data-testid="sale-receipt-datetime">{{ when }}</span>
    </div>
    <div
      v-if="sale.customer_name"
      class="sale-receipt__meta"
    >
      <span data-testid="sale-receipt-customer">{{ $t('sale.document.customer') }}: {{ sale.customer_name }}</span>
    </div>
    <hr class="sale-receipt__rule">
    <table
      v-if="lines.length"
      class="sale-receipt__lines"
    >
      <thead>
        <tr data-testid="sale-receipt-head">
          <th>{{ $t('sale.document.item') }}</th>
          <th class="sale-receipt__num">
            {{ $t('sale.document.amount') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="line in lines"
          :key="line.id"
          data-testid="sale-receipt-line"
        >
          <td class="sale-receipt__line-name">
            <div>{{ line.name }}</div>
            <div class="sale-receipt__detail">
              {{ line.detail }}
            </div>
            <div
              v-if="line.note"
              class="sale-receipt__note"
            >
              {{ line.note }}
            </div>
          </td>
          <td class="sale-receipt__num">
            {{ line.amount }}
          </td>
        </tr>
      </tbody>
    </table>
    <div
      v-else
      class="sale-receipt__center sale-receipt__small"
      data-testid="sale-receipt-no-lines"
    >
      {{ $t('sale.document.noLines') }}
    </div>
    <hr class="sale-receipt__rule">
    <table class="sale-receipt__totals">
      <tbody>
        <tr data-testid="sale-receipt-total-row">
          <td>{{ $t('sale.document.subtotal') }}</td>
          <td class="sale-receipt__num">
            {{ money(sale.subtotal) }}
          </td>
        </tr>
        <tr
          v-for="tax in taxes"
          :key="tax.key"
          data-testid="sale-receipt-total-row"
        >
          <td>{{ tax.label }}</td>
          <td class="sale-receipt__num">
            {{ tax.amount }}
          </td>
        </tr>
        <tr
          class="sale-receipt__grand"
          data-testid="sale-receipt-total-row"
        >
          <td>{{ $t('sale.document.total') }}</td>
          <td class="sale-receipt__num">
            {{ money(sale.total) }}
          </td>
        </tr>
        <tr
          v-for="payment in payments"
          :key="payment.id"
          class="sale-receipt__pay"
          data-testid="sale-receipt-total-row"
        >
          <td>{{ payment.method }}</td>
          <td class="sale-receipt__num">
            {{ payment.amount }}
          </td>
        </tr>
        <tr
          v-if="showsChange"
          class="sale-receipt__pay"
          data-testid="sale-receipt-total-row"
        >
          <td>{{ $t('sale.document.change') }}</td>
          <td class="sale-receipt__num">
            {{ money(sale.change_total) }}
          </td>
        </tr>
      </tbody>
    </table>
    <template v-if="footer.length">
      <hr class="sale-receipt__rule">
      <div
        v-for="(text, index) in footer"
        :key="index"
        class="sale-receipt__center sale-receipt__footer"
        data-testid="sale-receipt-footer"
      >
        {{ text }}
      </div>
    </template>
  </article>
</template>

<style scoped>
/* The old `ok-receipt`: thermal paper (80 mm), black on white whatever the theme, monospace with
   tabular figures so the amounts line up. */
.sale-receipt {
  box-sizing: border-box;
  width: 80mm;
  max-width: 100%;
  margin: 0 auto;
  padding: 4mm 3mm;
  background: #fff;
  color: #000;
  font-family: 'Roboto Mono', ui-monospace, 'SFMono-Regular', Menlo, Consolas, monospace;
  font-size: 11px;
  line-height: 1.45;
  font-variant-numeric: tabular-nums;
}
.sale-receipt__center {
  text-align: center;
}
.sale-receipt__duplicate {
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0.08em;
  margin-bottom: 2mm;
}
.sale-receipt__name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.sale-receipt__small {
  font-size: 10px;
}
.sale-receipt__rule {
  border: none;
  border-top: 1px dashed #000;
  margin: 2mm 0;
}
.sale-receipt__meta {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
  font-size: 10px;
}
.sale-receipt__lines,
.sale-receipt__totals {
  width: 100%;
  border-collapse: collapse;
}
.sale-receipt__lines th,
.sale-receipt__lines td,
.sale-receipt__totals td {
  padding: 0.3mm 0;
  vertical-align: top;
}
.sale-receipt__lines thead th {
  font-size: 9px;
  text-transform: uppercase;
  text-align: left;
  border-bottom: 1px solid #000;
}
.sale-receipt__num,
.sale-receipt__lines th.sale-receipt__num {
  text-align: right;
  white-space: nowrap;
}
.sale-receipt__line-name {
  word-break: break-word;
}
.sale-receipt__detail {
  font-size: 9px;
  opacity: 0.85;
}
.sale-receipt__note {
  font-size: 9px;
  padding-left: 2mm;
  opacity: 0.8;
}
.sale-receipt__grand td {
  font-size: 14px;
  font-weight: 700;
  padding-top: 1mm;
}
.sale-receipt__pay td {
  font-size: 10px;
}
.sale-receipt__footer {
  font-size: 10px;
  white-space: pre-line;
}
</style>
