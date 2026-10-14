<script setup lang="ts">
// The filters of the Sales list (SALE-F28: status, payment, date, total; the old column filters): the
// funnel button with the count of filters in use, opening a panel (FormModal) with Status (Any ·
// Completed · Voided · Refunded), Payment (the server-searched picker), Date from–to (business days; a
// range replaces the period) and Total from–to (euros, as the person types them). A change applies at
// once (the page asks the server again); «Clear» drops them all; «Done» closes. An amount that is not
// one, or what the server refused (a 422 of the list), is said under its field.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../../composables/useT';
import { filterCount, invalidAmounts, SALE_STATUSES, type SalesFilterKey, type SalesFilterValues } from './filters';
import PaymentMethodPicker from './PaymentMethodPicker.vue';

const props = withDefaults(
  defineProps<{
    /** What the server refused, by query parameter: painted under its filter. */
    fieldErrors?: Readonly<Record<string, string>>;
  }>(),
  { fieldErrors: () => ({}) },
);

const values = defineModel<SalesFilterValues>({ required: true });

const t = useT();
const open = ref(false);

const count = computed(() => filterCount(values.value));

/** The message under each field: an amount that is not one, else what the server said. */
const errors = computed<Partial<Record<SalesFilterKey, string>>>(() => {
  const out: Partial<Record<SalesFilterKey, string>> = { ...(props.fieldErrors as Record<SalesFilterKey, string>) };
  for (const key of invalidAmounts(values.value)) out[key] = t('sale.sales.filters.amountInvalid');
  return out;
});
const refused = computed(() => Object.values(errors.value).some(Boolean));
const invalid = (key: SalesFilterKey) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

const DATES: readonly { key: SalesFilterKey; label: string }[] = [
  { key: 'date_from', label: 'sale.sales.filters.dateFrom' },
  { key: 'date_to', label: 'sale.sales.filters.dateTo' },
];
const TOTALS: readonly { key: SalesFilterKey; label: string }[] = [
  { key: 'total_min', label: 'sale.sales.filters.totalMin' },
  { key: 'total_max', label: 'sale.sales.filters.totalMax' },
];

/** A new value per change (the parent's object is never mutated); blank or «Any» drops it. */
function set(key: SalesFilterKey, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value).trim();
  const next: Partial<Record<SalesFilterKey, string>> = { ...values.value };
  if (text) next[key] = text;
  else delete next[key];
  values.value = next;
}

function clear(): void {
  values.value = {};
}
</script>

<template>
  <ion-button
    class="sale-filters__button"
    fill="outline"
    :color="refused ? 'danger' : 'medium'"
    data-testid="sales-filters"
    :data-invalid="refused ? 'true' : undefined"
    :aria-label="count ? $t('sale.sales.filters.count', { n: count }) : $t('sale.sales.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('sale.sales.filters.button') }}
    <ion-badge
      v-if="count"
      class="sale-filters__count"
      color="primary"
      data-testid="sales-filters-count"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('sale.sales.filters.title')"
    testid="sales-filters-panel"
    @submit="open = false"
  >
    <div class="sale-filters__fields">
      <ion-select
        data-testid="sales-filter-status"
        :label="$t('sale.sales.columns.status')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :value="values.status ?? ''"
        :error-text="errors.status"
        :class="invalid('status')"
        @ion-change="set('status', $event.detail.value)"
      >
        <ion-select-option value="">
          {{ $t('sale.sales.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="status in SALE_STATUSES"
          :key="status"
          :value="status"
        >
          {{ $t(`sale.sales.status.${status}`) }}
        </ion-select-option>
      </ion-select>
      <PaymentMethodPicker
        testid="sales-filter-payment"
        value-key="name"
        :model-value="values.payment_method_name ?? ''"
        :label="$t('sale.sales.columns.payment')"
        :any-label="$t('sale.sales.filters.any')"
        :error-text="errors.payment_method_name"
        @update:model-value="set('payment_method_name', $event)"
      />
      <div class="sale-filters__range">
        <ion-input
          v-for="field in DATES"
          :key="field.key"
          :data-testid="`sales-filter-${field.key}`"
          :label="$t(field.label)"
          label-placement="floating"
          fill="outline"
          mode="md"
          type="date"
          :value="values[field.key] ?? ''"
          :error-text="errors[field.key]"
          :class="invalid(field.key)"
          @ion-change="set(field.key, $event.detail.value)"
        />
      </div>
      <div class="sale-filters__range">
        <ion-input
          v-for="field in TOTALS"
          :key="field.key"
          :data-testid="`sales-filter-${field.key}`"
          :label="$t(field.label)"
          label-placement="floating"
          fill="outline"
          mode="md"
          type="text"
          inputmode="decimal"
          :value="values[field.key] ?? ''"
          :debounce="300"
          :error-text="errors[field.key]"
          :class="invalid(field.key)"
          @ion-input="set(field.key, $event.detail.value)"
        />
      </div>
    </div>
    <template #footer>
      <ion-button
        fill="clear"
        class="sale-filters__clear"
        data-testid="sales-filters-clear"
        @click="clear"
      >
        {{ $t('sale.sales.filters.clear') }}
      </ion-button>
      <ion-button
        data-testid="sales-filters-done"
        @click="open = false"
      >
        {{ $t('sale.sales.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
/* Boxed like the table's own toolbar controls (38 px, radius 10). */
.sale-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
.sale-filters__button ion-icon {
  margin-inline-end: 0.35rem;
}
.sale-filters__count {
  margin-inline-start: 0.4rem;
}
.sale-filters__fields {
  display: grid;
  gap: 14px;
}
.sale-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.sale-filters__clear {
  --color: var(--ion-text-color);
}
</style>
