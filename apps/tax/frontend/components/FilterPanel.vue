<script lang="ts">
/** One choice of a closed-list filter. */
export interface FilterOption {
  value: string;
  label: string;
}

/**
 * A column filter: a text fragment (as long as the schema takes it), a choice of a short closed list
 * (plus «Any»), a choice among many with a searchbar (`search`: the page asks the server for what is
 * typed), or a from–to range (within the schema's bounds).
 */
export type FilterSpec =
  | { kind: 'text'; key: string; label: string; maxlength?: number }
  | { kind: 'select'; key: string; label: string; options: readonly FilterOption[] }
  | { kind: 'search'; key: string; label: string; options: readonly FilterOption[]; search?: (text: string) => void }
  | { kind: 'range'; key: string; label: string; keys: readonly [string, string]; min?: number; max?: number };

/** Filter values by the query parameter they fill; a filter not in use is absent. */
export type FilterValues = Readonly<Record<string, string>>;
</script>

<script setup lang="ts">
// The column filters of a tax list: the old table's funnel button, with the count of filters in use,
// opening its filters (here a dialog: FormModal) with one control per filter. A change applies at
// once (the page asks the server again); «Clear» drops them all; «Done» closes. Until the shared
// DataTable has its own column filters (UI-REQUESTS.md), each tax list puts this in its `filters` slot.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import SearchSelect from './SearchSelect.vue';

const props = withDefaults(
  defineProps<{
    filters: readonly FilterSpec[];
    /** Prefix of the hooks: `<testid>-filters`, `-filters-count`, `-filters-panel`, `-filter-<key>`… */
    testid: string;
    /** What the server refused, by query parameter (a 422 of the list): painted under its filter. */
    fieldErrors?: Readonly<Record<string, string>>;
  }>(),
  { fieldErrors: () => ({}) },
);

const values = defineModel<FilterValues>({ required: true });

const open = ref(false);

const keysOf = (filter: FilterSpec): readonly string[] => (filter.kind === 'range' ? filter.keys : [filter.key]);
const inUse = (key: string): boolean => (values.value[key] ?? '').trim() !== '';

/** Filters in use; a range counts once. */
const count = computed(() => props.filters.filter((f) => keysOf(f).some(inUse)).length);
/** The server refused a filter: the button says so until it is fixed. */
const refused = computed(() => props.filters.some((f) => keysOf(f).some((key) => !!props.fieldErrors[key])));
const invalid = (key: string) => ({ 'ion-invalid': !!props.fieldErrors[key], 'ion-touched': !!props.fieldErrors[key] });

/** What each searchable filter has typed (its `v-model:query`, when the server searches). */
const queries = ref<Record<string, string>>({});
function searchFor(filter: FilterSpec & { kind: 'search' }, text: string | undefined): void {
  queries.value = { ...queries.value, [filter.key]: text ?? '' };
  filter.search?.(text ?? '');
}

/** A new value per change (the parent's object is never mutated); blank or «Any» drops it. */
function set(key: string, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value).trim();
  const next: Record<string, string> = { ...values.value };
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
    class="tax-filters__button"
    fill="outline"
    :color="refused ? 'danger' : 'medium'"
    :data-testid="`${testid}-filters`"
    :data-invalid="refused ? 'true' : undefined"
    :aria-label="count ? $t('tax.filters.count', { n: count }) : $t('tax.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('tax.filters.button') }}
    <ion-badge
      v-if="count"
      class="tax-filters__count"
      color="primary"
      :data-testid="`${testid}-filters-count`"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('tax.filters.title')"
    :testid="`${testid}-filters-panel`"
    @submit="open = false"
  >
    <div class="tax-filters__fields">
      <template
        v-for="filter in filters"
        :key="filter.key"
      >
        <ion-input
          v-if="filter.kind === 'text'"
          :data-testid="`${testid}-filter-${filter.key}`"
          :label="filter.label"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="filter.maxlength"
          :value="values[filter.key] ?? ''"
          :debounce="300"
          :clear-input="true"
          :error-text="fieldErrors[filter.key]"
          :class="invalid(filter.key)"
          @ion-input="set(filter.key, $event.detail.value)"
        />
        <ion-select
          v-else-if="filter.kind === 'select'"
          :data-testid="`${testid}-filter-${filter.key}`"
          :label="filter.label"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :value="values[filter.key] ?? ''"
          :error-text="fieldErrors[filter.key]"
          :class="invalid(filter.key)"
          @ion-change="set(filter.key, $event.detail.value)"
        >
          <ion-select-option value="">
            {{ $t('tax.filters.any') }}
          </ion-select-option>
          <ion-select-option
            v-for="option in filter.options"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </ion-select-option>
        </ion-select>
        <SearchSelect
          v-else-if="filter.kind === 'search'"
          :testid="`${testid}-filter-${filter.key}`"
          :model-value="values[filter.key] ?? ''"
          :query="filter.search ? (queries[filter.key] ?? '') : undefined"
          :options="filter.options"
          :label="filter.label"
          :placeholder="$t('tax.filters.any')"
          :any-label="$t('tax.filters.any')"
          :error-text="fieldErrors[filter.key]"
          @update:model-value="set(filter.key, $event)"
          @update:query="searchFor(filter, $event)"
        />
        <div
          v-else
          class="tax-filters__range"
        >
          <ion-input
            v-for="(key, index) in filter.keys"
            :key="key"
            :data-testid="`${testid}-filter-${key}`"
            :label="`${filter.label} · ${index === 0 ? $t('tax.filters.from') : $t('tax.filters.to')}`"
            label-placement="floating"
            fill="outline"
            mode="md"
            type="number"
            inputmode="decimal"
            :min="filter.min"
            :max="filter.max"
            :value="values[key] ?? ''"
            :debounce="300"
            :error-text="fieldErrors[key]"
            :class="invalid(key)"
            @ion-input="set(key, $event.detail.value)"
          />
        </div>
      </template>
    </div>
    <template #footer>
      <ion-button
        fill="clear"
        class="tax-filters__clear"
        :data-testid="`${testid}-filters-clear`"
        @click="clear"
      >
        {{ $t('tax.filters.clear') }}
      </ion-button>
      <ion-button
        :data-testid="`${testid}-filters-done`"
        @click="open = false"
      >
        {{ $t('tax.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
/* Boxed like the table's own toolbar selects (38 px, radius 10). */
.tax-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
/* The funnel apart from its label, as the table's «+ Add». */
.tax-filters__button ion-icon {
  margin-inline-end: 0.35rem;
}
.tax-filters__count {
  margin-inline-start: 0.4rem;
}
.tax-filters__fields {
  display: grid;
  gap: 14px;
}
.tax-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.tax-filters__clear {
  --color: var(--ion-text-color);
}
</style>
