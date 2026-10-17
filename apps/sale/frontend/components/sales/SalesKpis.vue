<script setup lang="ts">
// The six figures of the period on Sales (SALE-F28; the old KPI cards): «Tickets», «Revenue» (refunds
// already taken off), «Avg. ticket», the tax, «Discounts» and «Voided», from `sale.sale.stats` over the same
// business days as the rows, followed live (a charge, a void or a refund re-runs it). The tax figure is named
// by the tax its sales were declared with (the stats' `tax_kind`: «VAT», «IGIC», «IPSI»), not by the
// territory kept today; sales of more than one tax make it a plain «Taxes». A period without sales, or
// figures not read yet, name it by the business territory's, as Taxes publishes it (`useTaxName`, live).
// A figure not read yet, or that could not be read, is «—», never a zero; a failure adds «Error loading
// metrics».
// The page mounts it only for whoever may see the reports (`sale.view_reports`).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { taxNameKey, useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney, formatQuantity } from '../../lib/format';
import type { StatsOut } from '../../operations';
import type { DayBounds } from './period';

const props = defineProps<{ bounds: DayBounds }>();

const t = useT();
const locale = useLocale();
const territoryTax = useTaxName();

const { data, error } = useLive('sale.sale.stats', () => ({ ...props.bounds }));

/** What the sales of the period declared; without sales (or figures), the territory's tax. */
const taxLabel = computed(() => {
  const stats = error.value ? undefined : data.value;
  if (!stats || stats.count === 0) return territoryTax.value;
  return stats.tax_kind ? t(taxNameKey(stats.tax_kind)) : t('sale.sales.kpis.taxes');
});

type Kind = 'count' | 'money';
/** Each card's label key; the tax's is `taxLabel`. */
const CARDS: readonly { key: string; label?: string; field: keyof StatsOut; kind: Kind }[] = [
  { key: 'tickets', label: 'sale.sales.kpis.tickets', field: 'count', kind: 'count' },
  { key: 'revenue', label: 'sale.sales.kpis.revenue', field: 'total_revenue', kind: 'money' },
  { key: 'avg-ticket', label: 'sale.sales.kpis.avgTicket', field: 'avg_ticket', kind: 'money' },
  { key: 'tax', field: 'tax_total', kind: 'money' },
  { key: 'discounts', label: 'sale.sales.kpis.discounts', field: 'discount_total', kind: 'money' },
  { key: 'voided', label: 'sale.sales.kpis.voided', field: 'voided_count', kind: 'count' },
];

const cards = computed(() =>
  CARDS.map((card) => {
    const stats = error.value ? undefined : data.value;
    const value = stats?.[card.field];
    let text = '—';
    if (typeof value === 'number') text = card.kind === 'money' ? formatMoney(value, locale.value) : formatQuantity(value, '', locale.value);
    return { key: card.key, label: card.label ? t(card.label) : taxLabel.value, text };
  }),
);
</script>

<template>
  <section
    class="sale-kpis"
    data-testid="sales-kpis"
    :aria-label="$t('sale.sales.kpis.label')"
  >
    <div
      v-for="card in cards"
      :key="card.key"
      class="sale-kpi"
    >
      <div
        class="sale-kpi__label"
        :data-testid="`sales-kpi-${card.key}-label`"
      >
        {{ card.label }}
      </div>
      <div
        class="sale-kpi__value"
        :data-testid="`sales-kpi-${card.key}`"
      >
        {{ card.text }}
      </div>
    </div>
  </section>
  <InlineFeedback
    v-if="error"
    class="sale-kpis__error"
    tone="danger"
    icon="alert-circle-outline"
    data-testid="sales-kpis-error"
  >
    {{ $t('sale.sales.kpis.error') }}
  </InlineFeedback>
</template>

<style scoped>
/* The old KPI cards: side by side, wrapping on a desk. */
.sale-kpis {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  margin-bottom: 1rem;
  min-width: 0;
}
.sale-kpi {
  flex: 1;
  min-width: 8rem;
  padding: 0.7rem 0.9rem;
  border: 1px solid var(--ion-border-color, #e0ddd4);
  border-radius: var(--ep-radius, 12px);
}
.sale-kpi__label {
  color: var(--ion-color-medium, #8b897f);
  font-size: 0.75rem;
  text-transform: uppercase;
}
.sale-kpi__value {
  font-size: 1.3rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}
.sale-kpis__error {
  margin-bottom: 1rem;
}
/* Below 768 px the six cards are ONE row that scrolls sideways (not three rows eating the screen). */
@media (max-width: 767.98px) {
  .sale-kpis {
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: thin;
  }
  .sale-kpi {
    flex: 0 0 auto;
  }
}
</style>
