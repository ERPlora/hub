<script setup lang="ts">
// The filters of the Invoices list (INVOICE-F16; the old column filters of status, type, date and total,
// plus series and source): the funnel button with the count of filters in use, opening a panel (FormModal)
// with Status, Type and Source (closed lists, already translated), Series (its code), Issued from–until and
// Total from–up to (euros, as the person types them). A change applies at once (the page asks the server
// again); «Clear filters» drops them all; «Done» closes. An amount that is not one, or what the server
// refused (a 422 of the list), is said under its field.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { SOURCE_CODES, STATUS_CODES, TYPE_CODES } from '../lib/invoice';
import { filterCount, type InvoiceFilterKey, type InvoiceFilterValues, invalidAmounts } from './filters';

const props = withDefaults(
  defineProps<{
    /** What the server refused, by query parameter: painted under its filter. */
    fieldErrors?: Readonly<Record<string, string>>;
  }>(),
  { fieldErrors: () => ({}) },
);

const values = defineModel<InvoiceFilterValues>({ required: true });

const t = useT();
const open = ref(false);

const count = computed(() => filterCount(values.value));

/** The message under each field: an amount that is not one, else what the server said. */
const errors = computed<Partial<Record<InvoiceFilterKey, string>>>(() => {
  const out: Partial<Record<InvoiceFilterKey, string>> = { ...(props.fieldErrors as Record<InvoiceFilterKey, string>) };
  for (const key of invalidAmounts(values.value)) out[key] = t('invoice.filters.amountInvalid');
  return out;
});
const refused = computed(() => Object.values(errors.value).some(Boolean));
const invalid = (key: InvoiceFilterKey) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

const SELECTS = computed(() => [
  { key: 'status' as const, label: t('invoice.filters.status'), options: STATUS_CODES.map((code) => ({ value: code, label: t(`invoice.status.${code}`) })) },
  { key: 'invoice_type' as const, label: t('invoice.filters.type'), options: TYPE_CODES.map((code) => ({ value: code, label: t(`invoice.typeNames.${code}`) })) },
  { key: 'source_type' as const, label: t('invoice.filters.source'), options: SOURCE_CODES.map((code) => ({ value: code, label: t(`invoice.sources.${code}`) })) },
]);
const DATES: readonly { key: InvoiceFilterKey; label: string }[] = [
  { key: 'issue_date_from', label: 'invoice.filters.dateFrom' },
  { key: 'issue_date_to', label: 'invoice.filters.dateTo' },
];
const TOTALS: readonly { key: InvoiceFilterKey; label: string }[] = [
  { key: 'total_amount_from', label: 'invoice.filters.totalFrom' },
  { key: 'total_amount_to', label: 'invoice.filters.totalTo' },
];

/** A new value per change (the parent's object is never mutated); blank or «Any» drops it. */
function set(key: InvoiceFilterKey, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value).trim();
  const next: Partial<Record<InvoiceFilterKey, string>> = { ...values.value };
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
    class="invoice-filters__button"
    fill="outline"
    :color="refused ? 'danger' : 'medium'"
    data-testid="invoice-filters"
    :data-invalid="refused ? 'true' : undefined"
    :aria-label="count ? $t('invoice.filters.count', { n: count }) : $t('invoice.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('invoice.filters.button') }}
    <ion-badge
      v-if="count"
      class="invoice-filters__count"
      color="primary"
      data-testid="invoice-filters-count"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('invoice.filters.title')"
    testid="invoice-filters-panel"
    @submit="open = false"
  >
    <div class="invoice-filters__fields">
      <ion-select
        v-for="select in SELECTS"
        :key="select.key"
        :data-testid="`invoice-filter-${select.key}`"
        :label="select.label"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :value="values[select.key] ?? ''"
        :error-text="errors[select.key]"
        :class="invalid(select.key)"
        @ion-change="set(select.key, $event.detail.value)"
      >
        <ion-select-option value="">
          {{ $t('invoice.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="option in select.options"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </ion-select-option>
      </ion-select>
      <ion-input
        data-testid="invoice-filter-series_code"
        :label="$t('invoice.filters.series')"
        label-placement="floating"
        fill="outline"
        mode="md"
        autocapitalize="characters"
        :maxlength="20"
        :value="values.series_code ?? ''"
        :debounce="300"
        :error-text="errors.series_code"
        :class="invalid('series_code')"
        @ion-input="set('series_code', $event.detail.value)"
      />
      <div class="invoice-filters__range">
        <ion-input
          v-for="field in DATES"
          :key="field.key"
          :data-testid="`invoice-filter-${field.key}`"
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
      <div class="invoice-filters__range">
        <ion-input
          v-for="field in TOTALS"
          :key="field.key"
          :data-testid="`invoice-filter-${field.key}`"
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
        class="invoice-filters__clear"
        data-testid="invoice-filters-clear"
        @click="clear"
      >
        {{ $t('invoice.filters.clear') }}
      </ion-button>
      <ion-button
        data-testid="invoice-filters-done"
        @click="open = false"
      >
        {{ $t('invoice.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
/* Boxed like the table's own toolbar controls (38 px, radius 10). */
.invoice-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
.invoice-filters__button ion-icon {
  margin-inline-end: 0.35rem;
}
.invoice-filters__count {
  margin-inline-start: 0.4rem;
}
.invoice-filters__fields {
  display: grid;
  gap: 14px;
}
.invoice-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.invoice-filters__clear {
  --color: var(--ion-text-color);
}
</style>
