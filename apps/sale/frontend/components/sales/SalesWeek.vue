<script setup lang="ts">
// What was sold each of the last seven business days, today last (SALE-F28; the old Home's «Last 7 days» panel,
// SALE-G01), from `sale.sale.last_7_days`, followed live (a charge, a void or a refund re-runs it). Sales shows it
// under the figures when the period is «7 days», to whoever may see the reports. A day without sales says 0; a
// failure says so.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { useLocale } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';

const locale = useLocale();
const business = useBusinessMoney();
const { data, error } = useLive('sale.sale.last_7_days', {});

/** «mié 14»: the weekday and the day of the month, in the reader's language (a business day is a date). */
const dayLabel = (iso: string) =>
  new Intl.DateTimeFormat(locale.value, { weekday: 'short', day: 'numeric', timeZone: 'UTC' }).format(new Date(`${iso}T00:00:00Z`));
const days = computed(() =>
  (error.value ? [] : (data.value?.rows ?? [])).map((row) => ({ day: row.day, label: dayLabel(row.day), total: formatMoney(row.total, locale.value, business.value) })),
);
</script>

<template>
  <InlineFeedback
    v-if="error"
    tone="danger"
    data-testid="sale-week-error"
  >
    {{ $t('sale.sales.week.loadFailed') }}
  </InlineFeedback>
  <ul
    v-else-if="days.length"
    class="sale-week"
    :aria-label="$t('sale.sales.week.title')"
    data-testid="sale-week"
  >
    <li
      v-for="day in days"
      :key="day.day"
      class="sale-week__day"
      data-testid="sale-week-day"
    >
      <span class="sale-week__label">{{ day.label }}</span>
      <span class="sale-week__total">{{ day.total }}</span>
    </li>
  </ul>
</template>

<style scoped>
.sale-week {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0 0 1rem;
  padding: 0;
  list-style: none;
}
.sale-week__day {
  display: grid;
  gap: 0.15rem;
  min-width: 0;
  padding: 0.5rem 0.6rem;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
}
.sale-week__label {
  font-size: 0.75rem;
  color: var(--ion-color-medium-shade, #636469);
  text-transform: capitalize;
}
.sale-week__total {
  overflow: hidden;
  font-size: 0.9rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  text-overflow: ellipsis;
}
@media (max-width: 820px) {
  .sale-week {
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }
}
@media (max-width: 420px) {
  .sale-week {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
