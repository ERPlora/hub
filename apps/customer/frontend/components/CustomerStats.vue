<script setup lang="ts">
// The four figures above the customer list (WORKBOOK «Pantallas · Clientes»): Customers, Active,
// VIP and Revenue (in the business's currency: customer-business-currency), followed live from
// `customer.customer.stats`; a write anywhere re-runs it on the server. The cards are the product's `ok-kpi` (label over a big value) rebuilt here until
// `@erplora/ui` has a KPI card (UI-REQUESTS.md).
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { formatMoney, useBusinessMoney } from '../lib/money';
import { useCustomerI18n } from '../lib/useCustomerI18n';

const { locale } = useCustomerI18n();
const { data, status } = useLive('customer.customer.stats', {});
const money = useBusinessMoney();

const loading = computed(() => data.value === undefined);

const figures = computed(() => {
  const stats = data.value;
  return [
    { id: 'total', label: 'customer.stats.customers', raw: stats?.total, text: stats ? String(stats.total) : '…' },
    { id: 'active', label: 'customer.stats.active', raw: stats?.active, text: stats ? String(stats.active) : '…' },
    { id: 'vip', label: 'customer.stats.vip', raw: stats?.vip, text: stats ? String(stats.vip) : '…' },
    {
      id: 'revenue',
      label: 'customer.stats.revenue',
      raw: stats?.total_revenue,
      text: stats ? formatMoney(stats.total_revenue, locale.value, money.value) : '…',
    },
  ];
});
</script>

<template>
  <div
    class="customer-stats"
    data-testid="customer-stats"
    role="group"
    :aria-label="$t('customer.stats.label')"
    :aria-busy="loading ? 'true' : 'false'"
  >
    <p
      v-if="status === 'error' && !data"
      class="customer-stats__error"
      data-testid="customer-stats-error"
      role="alert"
    >
      {{ $t('customer.stats.loadError') }}
    </p>
    <template v-else>
      <div
        v-for="figure in figures"
        :key="figure.id"
        class="customer-kpi"
        :data-testid="`customer-stats-${figure.id}`"
        :data-value="figure.raw"
      >
        <p class="customer-kpi__label">
          {{ $t(figure.label) }}
        </p>
        <p class="customer-kpi__value">
          {{ figure.text }}
        </p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.customer-stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  gap: 0.5rem;
  margin: 0 0 1rem;
}

/* The product's `ok-kpi`: a card with the label (muted, uppercase) over the value (big, bold). */
.customer-kpi {
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  padding: 1rem 1.125rem;
  background: var(--ep-card-background, var(--ion-card-background, var(--ion-background-color, #fff)));
  color: var(--ion-text-color, #1f2933);
  border: 1px solid var(--ep-border-color, var(--ion-border-color, rgba(0, 0, 0, 0.08)));
  border-radius: var(--ep-radius, 12px);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08), 0 1px 2px rgba(0, 0, 0, 0.04);
}

.customer-kpi__label {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--ep-medium, var(--ion-color-medium, #92949c));
}

.customer-kpi__value {
  margin: 0;
  font-size: 1.75rem;
  font-weight: 700;
  line-height: 1.1;
}

.customer-stats__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
