<script setup lang="ts">
// The breakdown and the totals of an open invoice (INVOICE-F17; the old detail's «Base / Impuestos /
// Total»): one row per tax of the breakdown with its base and its amount («VAT 21%», «Equivalence surcharge
// 5.2%», «Exempt (E1)», «Not subject», «Reverse charge»), then «Base», «Taxes» and «Total». The figures are
// the server's; this only writes them in the page's language.
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMoney, moneyOf } from '../lib/format';
import { taxRows } from '../lib/invoice';
import type { InvoiceOut } from '../operations';

const props = defineProps<{ invoice: Pick<InvoiceOut, 'tax_breakdown' | 'base_amount' | 'tax_amount' | 'total_amount' | 'currency' | 'currency_decimals'> }>();

const t = useT();
const locale = useLocale();
const money = (cents: number) => formatMoney(cents, locale.value, moneyOf(props.invoice));

const taxes = computed(() => taxRows(props.invoice.tax_breakdown, t, locale.value));
</script>

<template>
  <div class="invoice-totals">
    <ul class="invoice-totals__taxes">
      <li
        v-for="(row, index) in taxes"
        :key="index"
        data-testid="invoice-detail-tax"
      >
        <span data-testid="invoice-detail-tax-label">{{ row.label }} <span class="invoice-totals__base">({{ money(row.base) }})</span></span>
        <span
          class="invoice-totals__amount"
          data-testid="invoice-detail-tax-amount"
        >{{ money(row.amount) }}</span>
      </li>
    </ul>
    <div class="invoice-totals__sums">
      <span data-testid="invoice-detail-base">{{ $t('invoice.detail.totals.base') }}: {{ money(invoice.base_amount) }}</span>
      <span data-testid="invoice-detail-taxes">{{ $t('invoice.detail.totals.taxes') }}: {{ money(invoice.tax_amount) }}</span>
      <span
        class="invoice-totals__total"
        data-testid="invoice-detail-total"
      >{{ $t('invoice.detail.totals.total') }}: {{ money(invoice.total_amount) }}</span>
    </div>
  </div>
</template>

<style scoped>
.invoice-totals {
  display: grid;
  gap: 0.5rem;
  margin-top: 0.6rem;
}
.invoice-totals__taxes {
  margin: 0;
  padding: 0;
  list-style: none;
  justify-self: end;
  min-width: min(22rem, 100%);
}
.invoice-totals__taxes li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.85rem;
}
.invoice-totals__base {
  color: var(--ion-color-medium, #8a8577);
}
.invoice-totals__amount {
  white-space: nowrap;
}
.invoice-totals__sums {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem 1.5rem;
  justify-content: flex-end;
  font-weight: 600;
}
.invoice-totals__total {
  white-space: nowrap;
}
</style>
