<script setup lang="ts">
// «What goes back» in the Refund window (SALE-F31 step 3; the old `refund-lines`): the sale's lines, each
// with a checkbox and its amount. Marking one says it goes back with the money: all that is left of it
// to begin with; with two or more whole units left, «Units that go back» narrows it (1…left). A line
// partly returned says «<n> of <m> already returned»; one returned whole says «Already returned» and
// cannot be marked. What is left of each line is the server's (`sale.refund.options`). A line a voucher
// paid (SALE-F32) says «Already paid · <voucher>» instead of its amount and, marked, that its session goes
// back to that voucher.
import { IonCheckbox, IonInput } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney, formatQuantity, type Money } from '../../lib/format';
import type { LineOption } from '../../operations';
import { milli, type Picked, wholeLeft } from './refund';

/** `money`: the sale's own currency, the one its lines were charged in. */
const props = defineProps<{ lines: readonly LineOption[]; money?: Money }>();

/** Units marked per line, in thousandths of a unit. */
const picked = defineModel<Picked>('picked', { required: true });

const locale = useLocale();
const t = useT();

const rows = computed(() =>
  props.lines.map((line) => {
    const left = milli(line.left);
    const returned = milli(line.returned);
    const units = picked.value[line.line_id] ?? 0;
    return {
      line,
      done: left <= 0,
      partly: left > 0 && returned > 0,
      returned: formatQuantity(line.returned, '', locale.value),
      total: formatQuantity(line.quantity, '', locale.value),
      amount: line.paid_by_voucher ? t('sale.refund.linePaidWithVoucher', { name: line.voucher_name }) : formatMoney(line.line_total, locale.value, props.money),
      marked: units > 0,
      whole: wholeLeft(line),
      units: String(Math.round(units / 1000)),
    };
  }),
);

function mark(line: LineOption, on: boolean): void {
  const next: Record<string, number> = { ...picked.value };
  if (on && milli(line.left) > 0) next[line.line_id] = milli(line.left);
  else delete next[line.line_id];
  picked.value = next;
}

function setUnits(line: LineOption, typed: unknown): void {
  const most = wholeLeft(line);
  const units = Math.round(Number(typed));
  if (!picked.value[line.line_id] || most < 1 || !Number.isFinite(units) || typed === '' || typed === null) return;
  picked.value = { ...picked.value, [line.line_id]: Math.min(Math.max(1, units), most) * 1000 };
}
</script>

<template>
  <section
    class="sale-refund-lines"
    data-testid="refund-lines"
  >
    <div
      class="sale-refund-lines__title"
      data-testid="refund-lines-title"
    >
      {{ $t('sale.refund.linesTitle') }}
    </div>
    <p
      class="sale-refund-lines__hint"
      data-testid="refund-lines-hint"
    >
      {{ $t('sale.refund.linesHint') }}
    </p>
    <ul class="sale-refund-lines__list">
      <li
        v-for="row in rows"
        :key="row.line.line_id"
        class="sale-refund-lines__line"
        :data-testid="`refund-line-${row.line.line_id}`"
      >
        <div class="sale-refund-lines__main">
          <ion-checkbox
            :data-testid="`refund-line-check-${row.line.line_id}`"
            label-placement="end"
            justify="start"
            :checked="row.marked"
            :disabled="row.done"
            @ion-change="mark(row.line, $event.detail.checked === true)"
          >
            {{ row.line.name }}
          </ion-checkbox>
          <span
            :class="row.done ? 'sale-refund-lines__done' : row.line.paid_by_voucher ? 'sale-refund-lines__voucher' : 'sale-refund-lines__amount'"
            :data-testid="`refund-line-amount-${row.line.line_id}`"
          >{{ row.done ? $t('sale.refund.lineAlreadyReturned') : row.amount }}</span>
        </div>
        <span
          v-if="row.marked && row.line.paid_by_voucher"
          class="sale-refund-lines__session"
          :data-testid="`refund-line-session-${row.line.line_id}`"
        >{{ $t('sale.refund.sessionGoesBack', { name: row.line.voucher_name }) }}</span>
        <span
          v-if="row.partly"
          class="sale-refund-lines__done"
          :data-testid="`refund-line-partly-${row.line.line_id}`"
        >{{ $t('sale.refund.linePartlyReturned', { returned: row.returned, total: row.total }) }}</span>
        <ion-input
          v-if="row.marked && row.whole >= 2"
          class="sale-refund-lines__units"
          :data-testid="`refund-line-units-${row.line.line_id}`"
          :label="$t('sale.refund.lineUnits')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          type="number"
          inputmode="numeric"
          :min="1"
          :max="row.whole"
          :step="'1'"
          :value="row.units"
          @ion-input="setUnits(row.line, $event.detail.value)"
        />
      </li>
    </ul>
  </section>
</template>

<style scoped>
.sale-refund-lines__session {
  font-size: 0.85rem;
  color: var(--ion-color-success-shade, #1e8e3e);
}
.sale-refund-lines__title {
  font-weight: 600;
}
.sale-refund-lines__hint {
  margin: 0.25rem 0 0.5rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
}
.sale-refund-lines__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.4rem;
}
.sale-refund-lines__line {
  display: grid;
  gap: 0.3rem;
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--ion-border-color, #e0ddd4);
  border-radius: 10px;
}
.sale-refund-lines__main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.sale-refund-lines__amount {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
/* «Already paid · <voucher>»: a long name wraps instead of widening the window. */
.sale-refund-lines__voucher {
  min-width: 0;
  overflow-wrap: anywhere;
  text-align: right;
  color: var(--ion-color-success-shade, #1e8e3e);
  font-size: 0.85rem;
}
.sale-refund-lines__done {
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
}
.sale-refund-lines__units {
  max-width: 12rem;
}
</style>
