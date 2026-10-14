<script setup lang="ts">
// The open price's fallback when the business has no departments (SALE-F09): Taxes' active categories
// by name, each with today's rate, 20 at a time and searched on the server; a tap chooses one by key.
// With none at all, «No departments configured.».
import { useLive } from '@erplora/ui/sdk';
import { IonSearchbar, IonSpinner } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useLocale } from '../../composables/useT';
import { formatPercent } from '../../lib/format';
import type { OpenPriceChoice } from './DepartmentPicker.vue';

const choice = defineModel<OpenPriceChoice | null>({ required: true });

const locale = useLocale();
const term = shallowRef('');
const { data, status, error } = useLive('tax.category.list', () => ({
  search: term.value,
  sort: 'display_name' as const,
  dir: 'asc' as const,
  limit: 20,
  offset: 0,
}));

const rows = computed(() => (data.value?.rows ?? []).filter((row) => row.is_active));

function onInput(event: CustomEvent<{ value?: string | null }>): void {
  term.value = (event.detail.value ?? '').trim();
}
</script>

<template>
  <div class="pos-choices">
    <ion-searchbar
      class="pos-choices__search"
      :placeholder="$t('sale.pos.departmentSearch')"
      :debounce="250"
      :maxlength="120"
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
    >
      {{ error.message }}
    </p>
    <p
      v-else-if="!rows.length"
      class="pos-choices__state"
      data-testid="pos-tax-categories-none"
    >
      {{ $t('sale.pos.noDepartments') }}
    </p>
    <div
      v-else
      class="pos-choices__grid"
    >
      <button
        v-for="row in rows"
        :key="row.key"
        type="button"
        class="pos-choice"
        :data-testid="`pos-tax-category-${row.key}`"
        :aria-pressed="choice?.kind === 'tax' && choice.key === row.key ? 'true' : 'false'"
        @click="choice = { kind: 'tax', key: row.key, name: row.display_name || row.name }"
      >
        <span class="pos-choice__name">{{ row.display_name || row.name }}</span>
        <span
          v-if="row.rate_pct !== null"
          class="pos-choice__rate"
        >{{ formatPercent(row.rate_pct, locale) }}</span>
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
