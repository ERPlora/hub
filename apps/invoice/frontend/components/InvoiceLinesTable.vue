<script setup lang="ts">
// The lines of an open invoice (INVOICE-F17; the old detail's table): «#», «Description», «Qty», «Price»
// (WITHOUT VAT, RD 1619/2012 art. 6.1.f), «Disc.» when a line has one, «VAT %» (and the equivalence surcharge
// next to it), «Base», «Tax», «Total»; every figure the server's,
// written in the page's language (a rectifying line with its sign, in the quantity and the amounts). When
// its box is narrower than the eight columns (a phone, a split pane), each line becomes a block whose cells
// name their column. Without lines, «No detail lines.».
import { computed } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMoney, formatPercent, formatQuantity, formatUnitPrice } from '../lib/format';
import type { InvoiceLineOut } from '../operations';

const props = defineProps<{ lines: readonly InvoiceLineOut[] }>();

const t = useT();
const locale = useLocale();

/** «Disc.» only when a line has a discount (the price is before it, without VAT). */
const discounted = computed(() => props.lines.some((line) => line.discount_amount));

const headers = computed(() => [
  t('invoice.detail.lines.index'),
  t('invoice.detail.lines.description'),
  t('invoice.detail.lines.qty'),
  t('invoice.detail.lines.price'),
  ...(discounted.value ? [t('invoice.detail.lines.discount')] : []),
  t('invoice.detail.lines.taxPct'),
  t('invoice.detail.lines.base'),
  t('invoice.detail.lines.tax'),
  t('invoice.detail.lines.total'),
]);

const rows = computed(() =>
  props.lines.map((line) => {
    const surcharge = Number(line.surcharge_rate) > 0 ? ` + ${formatPercent(line.surcharge_rate, locale.value)}` : '';
    const discount = line.discount_amount ? formatMoney(line.discount_amount, locale.value) : '';
    return {
      id: line.id,
      cells: [
        String(line.position),
        line.description,
        formatQuantity(line.quantity, locale.value),
        formatUnitPrice(line.unit_price, locale.value),
        ...(discounted.value ? [discount] : []),
        `${formatPercent(line.tax_rate, locale.value)}${surcharge}`,
        formatMoney(line.base_amount, locale.value),
        formatMoney(line.tax_amount, locale.value),
        formatMoney(line.total_amount, locale.value),
      ],
    };
  }),
);
</script>

<template>
  <div class="invoice-lines">
    <table
      v-if="rows.length"
      class="invoice-lines__table"
      data-testid="invoice-detail-lines"
    >
      <thead>
        <tr>
          <th
            v-for="header in headers"
            :key="header"
          >
            {{ header }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id"
          data-testid="invoice-line-row"
        >
          <td
            v-for="(cell, index) in row.cells"
            :key="index"
            :class="{ 'invoice-lines__index': index === 0, 'invoice-lines__description': index === 1 }"
            :data-label="headers[index]"
          >
            {{ cell }}
          </td>
        </tr>
      </tbody>
    </table>
    <p
      v-else
      class="invoice-lines__none"
      data-testid="invoice-detail-no-lines"
    >
      {{ $t('invoice.detail.lines.none') }}
    </p>
  </div>
</template>

<style scoped>
/* The box is the container: the rule follows the room the detail really has, not the window. */
.invoice-lines {
  container-type: inline-size;
}
.invoice-lines__table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.5rem;
  font-size: 0.9rem;
}
.invoice-lines__table th,
.invoice-lines__table td {
  padding: 0.35rem 0.5rem;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
  text-align: right;
  white-space: nowrap;
}
.invoice-lines__table th:nth-child(-n + 2),
.invoice-lines__table td:nth-child(-n + 2) {
  text-align: left;
}
.invoice-lines__description {
  white-space: normal;
  word-break: break-word;
}
.invoice-lines__none {
  color: var(--ion-color-medium, #8a8577);
}
@container (max-width: 38rem) {
  .invoice-lines__table thead {
    display: none;
  }
  .invoice-lines__table,
  .invoice-lines__table tbody {
    display: block;
  }
  .invoice-lines__table tr {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    column-gap: 0.5rem;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
  }
  .invoice-lines__table td {
    display: flex;
    justify-content: space-between;
    gap: 0.75rem;
    grid-column: 1 / -1;
    padding: 0.15rem 0;
    border-bottom: 0;
  }
  .invoice-lines__table td::before {
    content: attr(data-label);
    text-align: left;
    color: var(--ion-color-medium, #8a8577);
  }
  .invoice-lines__table td.invoice-lines__index {
    grid-column: 1;
    font-weight: 600;
  }
  .invoice-lines__table td.invoice-lines__description {
    grid-column: 2;
    justify-content: flex-start;
    font-weight: 600;
  }
  .invoice-lines__table td.invoice-lines__index::before,
  .invoice-lines__table td.invoice-lines__description::before {
    content: none;
  }
}
</style>
