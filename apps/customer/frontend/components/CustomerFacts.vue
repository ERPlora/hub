<script setup lang="ts">
// The card's data, read-only (CUSTOMER-F03): the product's sheet (`dl.meta`) — Email, Phone, Tax ID,
// Company, Address, Stage, Source, Preferred channel, Purchases, Spent (in the business's currency:
// customer-business-currency), Last purchase, Active — and,
// new, the birthday, anniversary, internal notes and custom fields the product only showed when
// editing (WORKBOOK «Cambios frente al producto actual»).
import { formatDateTime } from '@erplora/ui/components';
import { computed } from 'vue';

import { countryName } from '../lib/countries';
import { formatDay } from '../lib/dates';
import { formatMoney, useBusinessMoney } from '../lib/money';
import { formatPhone } from '../lib/phoneDisplay';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomerDetailOut, CustomFieldValueOut } from '../operations';

const props = defineProps<{ customer: CustomerDetailOut }>();

const { t, locale } = useCustomerI18n();
const money = useBusinessMoney();

const dash = (value: string | null | undefined): string => (value && value.trim() ? value : '—');

const facts = computed(() => {
  const c = props.customer;
  const address = [c.address, c.postal_code, c.city, countryName(c.country, locale.value)].filter((p) => p && p.trim()).join(', ');
  return [
    { key: 'email', label: 'customer.detail.facts.email', value: dash(c.email) },
    { key: 'phone', label: 'customer.detail.facts.phone', value: dash(formatPhone(c.phone)) },
    { key: 'taxId', label: 'customer.detail.facts.taxId', value: dash(c.tax_id) },
    { key: 'company', label: 'customer.detail.facts.company', value: dash(c.company_name) },
    { key: 'address', label: 'customer.detail.facts.address', value: dash(address) },
    { key: 'stage', label: 'customer.detail.facts.stage', value: t(`customer.stage.${c.lifecycle_stage}`) },
    { key: 'source', label: 'customer.detail.facts.source', value: t(`customer.source.${c.source}`) },
    { key: 'channel', label: 'customer.detail.facts.preferredChannel', value: t(`customer.channel.${c.preferred_channel}`) },
    { key: 'purchases', label: 'customer.detail.facts.purchases', value: String(c.total_purchases) },
    { key: 'spent', label: 'customer.detail.facts.spent', value: formatMoney(c.total_spent, locale.value, money.value) },
    { key: 'lastPurchase', label: 'customer.detail.facts.lastPurchase', value: dash(formatDateTime(c.last_purchase_at, locale.value)) },
    { key: 'active', label: 'customer.detail.facts.active', value: c.is_active ? t('customer.common.yes') : t('customer.common.no') },
    { key: 'birthday', label: 'customer.detail.facts.birthday', value: formatDay(c.birthday, locale.value) },
    { key: 'anniversary', label: 'customer.detail.facts.anniversary', value: formatDay(c.anniversary, locale.value) },
    { key: 'notes', label: 'customer.detail.facts.notes', value: dash(c.notes), wide: true },
  ];
});

function fieldValue(field: CustomFieldValueOut): string {
  if (!field.value) return '—';
  if (field.field_type === 'boolean') return field.value === 'true' ? t('customer.common.yes') : t('customer.common.no');
  if (field.field_type === 'date') return formatDay(field.value, locale.value);
  return field.value;
}
</script>

<template>
  <div class="customer-facts-block">
    <dl
      class="customer-facts"
      data-testid="customer-facts"
    >
      <div
        v-for="fact in facts"
        :key="fact.key"
        class="customer-facts__item"
        :class="{ 'customer-facts__item--wide': fact.wide }"
        :data-fact="fact.key"
      >
        <dt>{{ $t(fact.label) }}</dt>
        <dd>{{ fact.value }}</dd>
      </div>
    </dl>
    <section
      v-if="customer.custom_fields.length"
      data-testid="customer-facts-custom"
    >
      <h3>{{ $t('customer.detail.facts.customFields') }}</h3>
      <dl class="customer-facts">
        <div
          v-for="field in customer.custom_fields"
          :key="field.field_id"
          class="customer-facts__item"
        >
          <dt>{{ field.name }}</dt>
          <dd>{{ fieldValue(field) }}</dd>
        </div>
      </dl>
    </section>
  </div>
</template>

<style scoped>
/* The product's `dl.meta`: small uppercase labels over bold values, in a responsive grid. */
.customer-facts {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
  gap: 0.25rem 0.75rem;
  margin: 0.5rem 0;
}

.customer-facts__item--wide {
  grid-column: 1 / -1;
}

.customer-facts dt {
  font-size: 0.72rem;
  text-transform: uppercase;
  opacity: 0.6;
}

.customer-facts dd {
  margin: 0 0 0.4rem;
  font-weight: 600;
  overflow-wrap: anywhere;
  white-space: pre-line;
}

h3 {
  margin: 0.75rem 0 0.25rem;
  font-size: 1rem;
}
</style>
