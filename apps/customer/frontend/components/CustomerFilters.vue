<script lang="ts">
import type { CustomerFilters as CustomerFilterParams, CustomerSource, CustomerStage } from '../operations';
import { centsFromEuros, readEuros } from '../lib/money';

/** The filters in use, as typed (a filter not in use is absent). Spent is in euros, as typed. */
export interface CustomerFilterValues {
  lifecycle_stage?: string;
  source?: string;
  is_active?: string;
  spent_from?: string;
  spent_to?: string;
}

/** An amount typed that is not one: said under its field, it neither counts nor filters. */
export const unreadableAmount = (text: string | undefined): boolean => readEuros(text).kind === 'invalid';

/** The filters that really apply (an amount it cannot read does not). */
export function filtersInUse(values: CustomerFilterValues): number {
  return Object.keys(filterParams(values)).length;
}

/** The filters as `customer.customer.list` takes them: a yes/no for active, cents for spent. */
export function filterParams(values: CustomerFilterValues): Partial<CustomerFilterParams> {
  const out: Partial<CustomerFilterParams> = {};
  if (values.lifecycle_stage) out.lifecycle_stage = values.lifecycle_stage as CustomerStage;
  if (values.source) out.source = values.source as CustomerSource;
  if (values.is_active) out.is_active = values.is_active === 'true';
  const min = centsFromEuros(values.spent_from);
  const max = centsFromEuros(values.spent_to);
  if (min !== undefined) out.spent_min = min;
  if (max !== undefined) out.spent_max = max;
  return out;
}
</script>

<script setup lang="ts">
// The filters of the customer list (CUSTOMER-F02): stage, source, active and spent by range, in
// euros. The product's table had them in its filter panel; here a «Filters» button with the count in
// use opens them in the shared FormModal (UI-REQUESTS.md asks the DataTable for column filters). A
// change applies at once (the page asks the server again); «Clear» drops them all; «Done» closes.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { STAGES } from '../lib/customerForm';

const values = defineModel<CustomerFilterValues>({ required: true });

const open = ref(false);
const SOURCES: CustomerSource[] = ['walk_in', 'phone', 'whatsapp', 'website', 'social', 'referral', 'import', 'other'];

const count = computed(() => filtersInUse(values.value));

/** A new object per change; blank or «Any» drops the filter. */
function set(key: keyof CustomerFilterValues, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value).trim();
  const next: CustomerFilterValues = { ...values.value };
  if (text) next[key] = text;
  else delete next[key];
  values.value = next;
}
</script>

<template>
  <ion-button
    class="customer-filters__button"
    size="small"
    fill="outline"
    color="medium"
    data-testid="customer-filters"
    :aria-label="count ? $t('customer.filters.count', { n: count }) : $t('customer.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('customer.filters.button') }}
    <ion-badge
      v-if="count"
      class="customer-filters__count"
      color="primary"
      data-testid="customer-filters-count"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    testid="customer-filters-panel"
    :title="$t('customer.filters.title')"
    @submit="open = false"
  >
    <div class="customer-filters__fields">
      <ion-select
        data-testid="customer-filter-stage"
        :label="$t('customer.list.filters.stage')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :value="values.lifecycle_stage ?? ''"
        @ion-change="set('lifecycle_stage', $event.detail.value)"
      >
        <ion-select-option value="">
          {{ $t('customer.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="stage in STAGES"
          :key="stage"
          :value="stage"
        >
          {{ $t(`customer.stage.${stage}`) }}
        </ion-select-option>
      </ion-select>
      <ion-select
        data-testid="customer-filter-source"
        :label="$t('customer.list.filters.source')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :value="values.source ?? ''"
        @ion-change="set('source', $event.detail.value)"
      >
        <ion-select-option value="">
          {{ $t('customer.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="origin in SOURCES"
          :key="origin"
          :value="origin"
        >
          {{ $t(`customer.source.${origin}`) }}
        </ion-select-option>
      </ion-select>
      <ion-select
        data-testid="customer-filter-active"
        :label="$t('customer.list.filters.active')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :value="values.is_active ?? ''"
        @ion-change="set('is_active', $event.detail.value)"
      >
        <ion-select-option value="">
          {{ $t('customer.filters.any') }}
        </ion-select-option>
        <ion-select-option value="true">
          {{ $t('customer.list.filters.activeOnly') }}
        </ion-select-option>
        <ion-select-option value="false">
          {{ $t('customer.list.filters.inactiveOnly') }}
        </ion-select-option>
      </ion-select>
      <div class="customer-filters__range">
        <ion-input
          data-testid="customer-filter-spent-from"
          :label="$t('customer.list.filters.spentFrom')"
          label-placement="floating"
          fill="outline"
          mode="md"
          inputmode="decimal"
          :value="values.spent_from ?? ''"
          :debounce="300"
          :error-text="unreadableAmount(values.spent_from) ? $t('customer.filters.amountInvalid') : undefined"
          :class="{ 'ion-invalid': unreadableAmount(values.spent_from), 'ion-touched': unreadableAmount(values.spent_from) }"
          @ion-input="set('spent_from', $event.detail.value)"
        />
        <ion-input
          data-testid="customer-filter-spent-to"
          :label="$t('customer.list.filters.spentTo')"
          label-placement="floating"
          fill="outline"
          mode="md"
          inputmode="decimal"
          :value="values.spent_to ?? ''"
          :debounce="300"
          :error-text="unreadableAmount(values.spent_to) ? $t('customer.filters.amountInvalid') : undefined"
          :class="{ 'ion-invalid': unreadableAmount(values.spent_to), 'ion-touched': unreadableAmount(values.spent_to) }"
          @ion-input="set('spent_to', $event.detail.value)"
        />
      </div>
    </div>
    <template #footer>
      <ion-button
        fill="clear"
        data-testid="customer-filters-clear"
        :disabled="!count"
        @click="values = {}"
      >
        {{ $t('customer.filters.clear') }}
      </ion-button>
      <ion-button
        data-testid="customer-filters-done"
        @click="open = false"
      >
        {{ $t('customer.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.customer-filters__button {
  margin: 0;
}

.customer-filters__count {
  margin-inline-start: 0.4rem;
}

.customer-filters__fields {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.customer-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}
</style>
