<script setup lang="ts">
// The filters of the sessions list (the old column filters: status, number and the four amounts): the
// funnel button with the count of filters in use, opening a panel with Status (Any · Open · Closed),
// Session number and Opening, Expected, Counted and Difference from–to, typed as money (the difference
// may be negative: a short drawer). A change applies at once (the page asks the server again); «Clear»
// drops them all; «Done» closes. An amount that is not one, or what the server refused, is said under it.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { filterCount, invalidAmounts, SESSION_STATUSES, type SessionFilterKey, type SessionFilterValues } from '../lib/filters';

const props = withDefaults(
  defineProps<{
    /** What the server refused, by query parameter: painted under its filter. */
    fieldErrors?: Readonly<Record<string, string>>;
  }>(),
  { fieldErrors: () => ({}) },
);

const values = defineModel<SessionFilterValues>({ required: true });

const t = useT();
const open = ref(false);

const count = computed(() => filterCount(values.value));

const errors = computed<Partial<Record<SessionFilterKey, string>>>(() => {
  const out: Partial<Record<SessionFilterKey, string>> = { ...(props.fieldErrors as Record<SessionFilterKey, string>) };
  for (const key of invalidAmounts(values.value)) out[key] = t('cash_register.filters.amountInvalid');
  return out;
});
const refused = computed(() => Object.values(errors.value).some(Boolean));
const invalid = (key: SessionFilterKey) => ({ 'ion-invalid': !!errors.value[key], 'ion-touched': !!errors.value[key] });

const RANGES = ['opening', 'expected', 'counted', 'difference'] as const;

/** A new value per change (the parent's object is never mutated); blank or «Any» drops it. */
function set(key: SessionFilterKey, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value).trim();
  const next: Partial<Record<SessionFilterKey, string>> = { ...values.value };
  if (text) next[key] = text;
  else delete next[key];
  values.value = next;
}
</script>

<template>
  <ion-button
    class="cash-filters__button"
    fill="outline"
    :color="refused ? 'danger' : 'medium'"
    data-testid="cash-register-filters"
    :aria-label="count ? $t('cash_register.filters.count', { n: count }) : $t('cash_register.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('cash_register.filters.button') }}
    <ion-badge
      v-if="count"
      class="cash-filters__count"
      color="primary"
      data-testid="cash-register-filters-count"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('cash_register.filters.title')"
    testid="cash-register-filters-panel"
    @submit="open = false"
  >
    <div class="cash-filters__fields">
      <ion-select
        data-testid="cash-register-filter-status"
        :label="$t('cash_register.filters.status')"
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
          {{ $t('cash_register.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="status in SESSION_STATUSES"
          :key="status"
          :value="status"
        >
          {{ $t(`cash_register.status.${status}`) }}
        </ion-select-option>
      </ion-select>
      <ion-input
        data-testid="cash-register-filter-number"
        :label="$t('cash_register.filters.number')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="24"
        :value="values.number ?? ''"
        :debounce="300"
        :error-text="errors.number"
        :class="invalid('number')"
        @ion-input="set('number', $event.detail.value)"
      />
      <fieldset
        v-for="range in RANGES"
        :key="range"
        class="cash-filters__range"
      >
        <legend>{{ $t(`cash_register.filters.${range}`) }}</legend>
        <ion-input
          v-for="edge in (['min', 'max'] as const)"
          :key="edge"
          :data-testid="`cash-register-filter-${range}_${edge}`"
          :label="edge === 'min' ? $t('cash_register.filters.from') : $t('cash_register.filters.to')"
          label-placement="floating"
          fill="outline"
          mode="md"
          type="text"
          inputmode="decimal"
          :value="values[`${range}_${edge}`] ?? ''"
          :debounce="300"
          :error-text="errors[`${range}_${edge}`]"
          :class="invalid(`${range}_${edge}`)"
          @ion-input="set(`${range}_${edge}`, $event.detail.value)"
        />
      </fieldset>
    </div>
    <template #footer>
      <ion-button
        fill="clear"
        data-testid="cash-register-filters-clear"
        @click="values = {}"
      >
        {{ $t('cash_register.filters.clear') }}
      </ion-button>
      <ion-button
        data-testid="cash-register-filters-done"
        @click="open = false"
      >
        {{ $t('cash_register.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
/* Boxed like the table's own toolbar controls (38 px, radius 10). */
.cash-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
.cash-filters__button ion-icon {
  margin-inline-end: 0.35rem;
}
.cash-filters__count {
  margin-inline-start: 0.4rem;
}
.cash-filters__fields {
  display: grid;
  gap: 0.75rem;
}
.cash-filters__range {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
  margin: 0;
  padding: 0;
  border: 0;
}
.cash-filters__range legend {
  margin-bottom: 0.25rem;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
