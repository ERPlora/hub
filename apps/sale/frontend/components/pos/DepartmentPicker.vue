<script lang="ts">
/** What an open-price line is charged at: a department of the business or, without any, a tax category. */
export type OpenPriceChoice = { kind: 'department'; id: string; name: string } | { kind: 'tax'; key: string; name: string };
</script>

<script setup lang="ts">
// «Department (VAT)» of the open-price sheet (SALE-F09): the business's departments in their order, each
// with the rate its category charges today, 20 at a time and searched on the server; a tap chooses one.
// A business without departments gets Taxes' categories instead (`TaxCategoryPicker`); a search that
// finds nothing is not «no departments». Mounted only while the sheet is open.
import { useLive } from '@erplora/ui/sdk';
import { IonSearchbar, IonSpinner } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useLocale } from '../../composables/useT';
import { formatPercent } from '../../lib/format';
import TaxCategoryPicker from './TaxCategoryPicker.vue';

const choice = defineModel<OpenPriceChoice | null>({ required: true });

const locale = useLocale();
const term = shallowRef('');
const { data, status, error } = useLive('sale.department.list', () => ({
  search: term.value,
  sort: 'sort_order' as const,
  dir: 'asc' as const,
  limit: 20,
  offset: 0,
}));

const rows = computed(() => data.value?.rows ?? []);
/** No departments at all (not a search that found none): Taxes' categories stand in. */
const none = computed(() => !term.value && data.value?.total === 0);

function onInput(event: CustomEvent<{ value?: string | null }>): void {
  term.value = (event.detail.value ?? '').trim();
}
</script>

<template>
  <TaxCategoryPicker
    v-if="none"
    v-model="choice"
  />
  <div
    v-else
    class="pos-choices"
  >
    <ion-searchbar
      class="pos-choices__search"
      :placeholder="$t('sale.pos.departmentSearch')"
      :debounce="250"
      :maxlength="60"
      @ion-input="onInput"
    />
    <div
      v-if="status === 'loading' && !rows.length"
      class="pos-choices__state"
    >
      <ion-spinner />
    </div>
    <p
      v-else-if="error"
      class="pos-choices__state pos-choices__state--error"
      role="alert"
      data-testid="pos-departments-error"
    >
      {{ $t('sale.pos.departmentsLoadFailed') }}
    </p>
    <p
      v-else-if="!rows.length"
      class="pos-choices__state"
      data-testid="pos-departments-none"
    >
      {{ $t('sale.pos.noDepartments') }}
    </p>
    <div
      v-else
      class="pos-choices__grid"
    >
      <button
        v-for="row in rows"
        :key="row.id"
        type="button"
        class="pos-choice"
        :data-testid="`pos-department-${row.id}`"
        :aria-pressed="choice?.kind === 'department' && choice.id === row.id ? 'true' : 'false'"
        @click="choice = { kind: 'department', id: row.id, name: row.name }"
      >
        <span class="pos-choice__name">{{ row.name }}</span>
        <span
          v-if="row.tax_rate_pct !== null"
          class="pos-choice__rate"
        >{{ formatPercent(row.tax_rate_pct, locale) }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.pos-choices__search {
  padding: 0 0 0.4rem;
}
.pos-choices__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.45rem;
}
.pos-choice {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.4rem;
  min-height: 3rem;
  padding: 0.5rem 0.65rem;
  font: inherit;
  font-size: 0.88rem;
  text-align: left;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
  cursor: pointer;
}
.pos-choice[aria-pressed='true'] {
  color: var(--ion-color-primary, #0091ce);
  background: color-mix(in srgb, var(--ion-color-primary, #0091ce) 10%, transparent);
  border-color: var(--ion-color-primary, #0091ce);
}
.pos-choice__name {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
}
.pos-choice__rate {
  flex: none;
  font-size: 0.78rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-choices__state {
  margin: 0;
  padding: 0.8rem;
  text-align: center;
  color: var(--ion-color-medium, #8b897f);
}
.pos-choices__state--error {
  color: var(--ion-color-danger, #d9480f);
}
</style>
