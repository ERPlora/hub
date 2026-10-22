<script setup lang="ts">
// The filters of a VeriFactu list (VERIFACTU-F16, F31): the funnel button with the count of filters in use,
// opening a panel (FormModal) with the closed lists already translated, the days and, in Records, the totals
// (euros, as the person types them). A change applies at once (the page asks the server again); «Clear filters»
// drops them all; «Done» closes. An amount that is not one is said under its field.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { ENVIRONMENTS, EVENT_KINDS, INVOICE_TYPES, RECORD_TYPES, SEVERITIES, STATUSES } from '../lib/record';
import { filterCount, type FilterValues, invalidAmounts } from './filters';

const props = defineProps<{
  /** Which list: its own filters. */
  list: 'records' | 'events';
}>();

const values = defineModel<FilterValues>({ required: true });

const t = useT();
const open = ref(false);
const count = computed(() => filterCount(values.value));

interface Select {
  key: string;
  label: string;
  options: { value: string; label: string }[];
}

const selects = computed<Select[]>(() =>
  props.list === 'records'
    ? [
        { key: 'status', label: t('verifactu.filters.status'), options: STATUSES.map((code) => ({ value: code, label: t(`verifactu.status.${code}`) })) },
        { key: 'record_type', label: t('verifactu.filters.type'), options: RECORD_TYPES.map((code) => ({ value: code, label: t(`verifactu.recordType.${code}`) })) },
        { key: 'invoice_type', label: t('verifactu.filters.invoiceType'), options: INVOICE_TYPES.map((code) => ({ value: code, label: code })) },
        { key: 'environment', label: t('verifactu.filters.environment'), options: ENVIRONMENTS.map((code) => ({ value: code, label: t(`verifactu.env.${code}`) })) },
      ]
    : [
        { key: 'kind', label: t('verifactu.filters.kind'), options: EVENT_KINDS.map((code) => ({ value: code, label: t(`verifactu.kind.${code}`) })) },
        { key: 'severity', label: t('verifactu.filters.severity'), options: SEVERITIES.map((code) => ({ value: code, label: t(`verifactu.severity.${code}`) })) },
      ],
);
const dates = computed(() =>
  props.list === 'records'
    ? [
        { key: 'issue_date_from', label: t('verifactu.filters.issuedFrom') },
        { key: 'issue_date_to', label: t('verifactu.filters.issuedTo') },
      ]
    : [
        { key: 'date_from', label: t('verifactu.filters.from') },
        { key: 'date_to', label: t('verifactu.filters.to') },
      ],
);
const amounts = computed(() =>
  props.list === 'records'
    ? [
        { key: 'total_amount_from', label: t('verifactu.filters.totalFrom') },
        { key: 'total_amount_to', label: t('verifactu.filters.totalTo') },
      ]
    : [],
);

const errors = computed<Record<string, string>>(() =>
  Object.fromEntries(invalidAmounts(values.value).map((key) => [key, t('verifactu.filters.amountInvalid')])),
);
const invalid = (key: string) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

/** A new value per change (the parent's object is never mutated); blank or «Any» drops it. */
function set(key: string, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value).trim();
  const next: FilterValues = { ...values.value };
  if (text) next[key] = text;
  else delete next[key];
  values.value = next;
}
</script>

<template>
  <ion-button
    class="verifactu-filters__button"
    fill="outline"
    color="medium"
    data-testid="verifactu-filters"
    :aria-label="count ? $t('verifactu.filters.count', { n: count }) : $t('verifactu.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('verifactu.filters.button') }}
    <ion-badge
      v-if="count"
      class="verifactu-filters__count"
      color="primary"
      data-testid="verifactu-filters-count"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('verifactu.filters.title')"
    testid="verifactu-filters-panel"
    @submit="open = false"
  >
    <div class="verifactu-filters__fields">
      <ion-select
        v-for="select in selects"
        :key="select.key"
        :data-testid="`verifactu-filter-${select.key}`"
        :label="select.label"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :value="values[select.key] ?? ''"
        @ion-change="set(select.key, $event.detail.value)"
      >
        <ion-select-option value="">
          {{ $t('verifactu.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="option in select.options"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </ion-select-option>
      </ion-select>
      <div class="verifactu-filters__range">
        <ion-input
          v-for="field in dates"
          :key="field.key"
          :data-testid="`verifactu-filter-${field.key}`"
          :label="field.label"
          label-placement="floating"
          fill="outline"
          mode="md"
          type="date"
          :value="values[field.key] ?? ''"
          @ion-change="set(field.key, $event.detail.value)"
        />
      </div>
      <div
        v-if="amounts.length"
        class="verifactu-filters__range"
      >
        <ion-input
          v-for="field in amounts"
          :key="field.key"
          :data-testid="`verifactu-filter-${field.key}`"
          :label="field.label"
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
        data-testid="verifactu-filters-clear"
        @click="values = {}"
      >
        {{ $t('verifactu.filters.clear') }}
      </ion-button>
      <ion-button
        data-testid="verifactu-filters-done"
        @click="open = false"
      >
        {{ $t('verifactu.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.verifactu-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
.verifactu-filters__count {
  margin-inline-start: 0.4rem;
}
.verifactu-filters__fields {
  display: grid;
  gap: 14px;
}
.verifactu-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
</style>
