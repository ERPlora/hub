<script setup lang="ts">
// The ticket of a sale as it prints (SALE-F29; the old `ok-receipt`, thermal paper 80 mm; a sale
// charged as a full invoice is titled «Invoice» and numbered «No.» instead of «Receipt»): the header
// from the receipt settings (first line = the name, else «My business»; the rest = the address),
// «DUPLICATE» on a reprint, the number with the date and time — the number Invoicing gave its ticket or
// invoice in the very charge («Invoice FACT-2026-000012»), the sale's own only while it has none, and
// then «Fiscal document pending» under it, so the paper never poses as issued —, the customer, the lines
// («qty × unit price», a gift «(On the house)», a line a voucher paid «Already paid · <voucher>»
// (SALE-F27), the note), «Subtotal», a VAT row per fiscal key from the sale's breakdown (an
// exempt key names its cause), «TOTAL», the payment rows and «Change», the discount already applied and
// the fiscal QR and the footer. Every figure is the server's; this only lays them out. The fiscal QR is
// VeriFactu's (VERIFACTU-F19, sales#411): «Tax QR:» over it, «VERI*FACTU» under it and how to check the ticket or
// the invoice at the AEAT — its CSV once the AEAT answered. `printPaper` prints a copy of this very element.
import { formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { taxRow } from '../../lib/breakdown';
import { dishLabel } from '../../lib/comboChoice';
import { formatMoney, formatQuantity, moneyOf } from '../../lib/format';
import type { SaleOut, SettingsOut } from '../../operations';
import type { FiscalRecord } from './FiscalRecordFollower.vue';

const props = withDefaults(
  defineProps<{
    sale: SaleOut;
    /** The receipt settings (`sale.pos_settings.get`); none = the default header and no footer. */
    settings?: Pick<SettingsOut, 'receipt_header' | 'receipt_footer'> | null;
    /** A reprint: «DUPLICATE» on top. */
    duplicate?: boolean;
    /** VeriFactu's record of its fiscal document; none = no fiscal QR. */
    record?: Pick<FiscalRecord, 'qr_svg' | 'qr_url' | 'csv'> | null;
  }>(),
  { settings: null, duplicate: false, record: null },
);

const t = useT();
const locale = useLocale();

/** The taxes the paper names short («IVA 10 %»); any other keeps the label its rule gave it. */
const TAX_NAMES = new Set(['vat', 'surcharge', 'igic', 'ipsi']);

const money = (cents: number): string => formatMoney(cents, locale.value, moneyOf(props.sale));

const header = computed(() => (props.settings?.receipt_header ?? '').split('\n').map((line) => line.trim()).filter(Boolean));
const businessName = computed(() => header.value[0] ?? t('sale.document.defaultBusiness'));
const address = computed(() => header.value.slice(1));
const when = computed(() => formatDateTime(props.sale.created_at, locale.value));
/** A sale charged as a full invoice says so on top and is numbered «No.», never «Receipt». */
const isInvoice = computed(() => props.sale.document_type === 'invoice');
/** The fiscal number Invoicing gave it («FACT-2026-000012»); the sale's own while it has none. */
const fiscalNumber = computed(() => props.sale.invoice_number || '');
const shownNumber = computed(() => fiscalNumber.value || props.sale.number);
const numberLabel = computed(() => {
  if (!isInvoice.value) return t('sale.document.receipt');
  return fiscalNumber.value ? t('sale.document.invoice') : t('sale.document.number');
});

/** A dish of a menu split per dish (SALE-F12): the menu's lines carry its product; one in one line does not. */
const isDishPart = (line: SaleOut['lines'][number]) => !!line.combo_id && line.product_id !== null;
const menuOf = (line: SaleOut['lines'][number]) => `${line.order_line_id}:${line.combo_id}`;

const lines = computed(() =>
  props.sale.lines.map((line, index) => ({
    id: line.id,
    // An option of another tax category hangs under its dish (SALE-F11): «+ <option>».
    name: `${line.parent_line_id ? '+ ' : ''}${line.is_gift ? `${line.name} ${t('sale.document.gift')}` : line.name}`,
    // The dishes of a split menu hang under its name, printed once over the first of them (SALE-F12).
    child: !!line.parent_line_id || isDishPart(line),
    head:
      isDishPart(line) && (index === 0 || menuOf(props.sale.lines[index - 1]) !== menuOf(line)) ? line.combo_name : '',
    // A menu in one line prints each of its dishes on a line of its own under it (hub#1165).
    dishes: line.combo_id && !isDishPart(line) ? line.components.map(dishLabel) : [],
    options: line.modifiers.join(', '),
    detail: `${formatQuantity(line.quantity, line.unit, locale.value)} × ${money(line.unit_price)}`,
    note: line.notes.trim(),
    voucher: line.paid_by_voucher ? t('sale.document.paidWithVoucher', { name: line.voucher_name }) : '',
    amount: money(line.line_total),
  })),
);

const taxWords = computed(() => ({
  locale: locale.value,
  taxName: (label: string) => (TAX_NAMES.has(label) ? t(`sale.document.taxes.${label}`) : label),
  qualification: (kind: string) => t(`sale.document.qualification.${kind}`),
}));
const taxes = computed(() =>
  props.sale.breakdown.map((row) => ({ ...taxRow(row, taxWords.value), amount: money(row.tax) })),
);

const payments = computed(() =>
  [...props.sale.payments]
    .sort((a, b) => a.position - b.position)
    .map((payment) => ({ id: payment.id, method: payment.method_name, amount: money(payment.tendered || payment.amount) })),
);
/** Change is given in cash: a cash tender always says it, 0 included. */
const showsChange = computed(() => props.sale.payments.some((payment) => payment.method_type === 'cash'));

/** Under the QR: the AEAT's CSV once it answered, else how to check what the customer holds. */
const qrHint = computed(() => {
  if (!props.record) return '';
  if (props.record.csv) return t('sale.document.qr.csv', { csv: props.record.csv });
  return isInvoice.value ? t('sale.document.qr.checkInvoice') : t('sale.document.qr.checkReceipt');
});

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
    <div
      v-if="isInvoice"
      class="sale-receipt__title"
      data-testid="sale-receipt-title"
    >
      {{ $t('sale.document.invoice') }}
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
      <span data-testid="sale-receipt-number">{{ numberLabel }}: <strong>{{ shownNumber }}</strong></span>
      <span data-testid="sale-receipt-datetime">{{ when }}</span>
    </div>
    <div
      v-if="sale.invoice_status === 'pending'"
      class="sale-receipt__meta"
    >
      <strong data-testid="sale-receipt-pending">{{ $t('sale.document.paperPending') }}</strong>
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
        <template
          v-for="line in lines"
          :key="line.id"
        >
          <tr
            v-if="line.head"
            data-testid="sale-receipt-menu-head"
          >
            <td
              class="sale-receipt__line-name"
              colspan="2"
            >
              {{ line.head }}
            </td>
          </tr>
          <tr data-testid="sale-receipt-line">
            <td
              class="sale-receipt__line-name"
              :class="{ 'sale-receipt__line-name--child': line.child }"
            >
              <div>{{ line.name }}</div>
              <div class="sale-receipt__detail">
                {{ line.detail }}
              </div>
              <div
                v-for="(dish, at) in line.dishes"
                :key="at"
                class="sale-receipt__detail sale-receipt__dish"
                data-testid="sale-receipt-dish"
              >
                {{ dish }}
              </div>
              <div
                v-if="line.options"
                class="sale-receipt__detail"
                data-testid="sale-receipt-options"
              >
                {{ line.options }}
              </div>
              <div
                v-if="line.voucher"
                class="sale-receipt__detail"
                data-testid="sale-receipt-voucher"
              >
                {{ line.voucher }}
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
        </template>
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
    <template v-if="record">
      <hr class="sale-receipt__rule">
      <div
        class="sale-receipt__qr"
        data-testid="sale-receipt-qr"
      >
        <div class="sale-receipt__center">
          {{ $t('sale.document.qr.label') }}
        </div>
        <img
          class="sale-receipt__qr-image"
          :src="record.qr_svg"
          :alt="$t('sale.document.qr.alt')"
        >
        <div class="sale-receipt__center sale-receipt__qr-mark">
          VERI*FACTU
        </div>
        <div
          class="sale-receipt__center sale-receipt__qr-hint"
          data-testid="sale-receipt-qr-hint"
        >
          {{ qrHint }}
        </div>
      </div>
    </template>
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
/* The document's title (a full invoice), as the old paper titled what is not a plain ticket. */
.sale-receipt__title {
  text-align: center;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 1mm;
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
.sale-receipt__line-name--child {
  padding-left: 0.75rem;
}
.sale-receipt__dish {
  padding-left: 0.75rem;
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
.sale-receipt__qr {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.2rem;
}
/* The AEAT asks for a QR between 30 and 40 mm a side. */
.sale-receipt__qr-image {
  width: 35mm;
  height: 35mm;
}
.sale-receipt__qr-mark {
  font-weight: 700;
}
.sale-receipt__qr-hint {
  font-size: 0.85em;
}
.sale-receipt__footer {
  font-size: 10px;
  white-space: pre-line;
}
</style>
