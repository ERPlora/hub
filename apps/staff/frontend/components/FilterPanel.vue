<script lang="ts">
import type { SearchOption } from './SearchSelect.vue';

/** One choice of a closed-list filter. */
export interface FilterOption {
  value: string;
  label: string;
}

/** A column filter: a text fragment, a choice of a closed list (plus «Any») or a from–to range. */
export type FilterSpec =
  | { kind: 'text'; key: string; label: string }
  | { kind: 'select'; key: string; label: string; options: readonly FilterOption[] }
  /** A long list (members, roles, accounts): a picker searched on the server. */
  | { kind: 'search'; key: string; label: string; load: (search: string) => Promise<SearchOption[]> }
  | { kind: 'range'; key: string; label: string; keys: readonly [string, string]; type?: 'number' | 'date' };

/** Filter values by the query parameter they fill; a filter not in use is absent. */
export type FilterValues = Readonly<Record<string, string>>;
</script>

<script setup lang="ts">
// The column filters of a staff list: the old table's funnel button, with the count of filters in
// use, opening its filters (here a dialog: FormModal) with one control per filter. A change applies at
// once (the page asks the server again); «Clear» drops them all; «Done» closes. Until the shared
// DataTable has its own column filters, each staff list puts this in its `filters` slot.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import SearchSelect from './SearchSelect.vue';

const props = defineProps<{
  filters: readonly FilterSpec[];
  /** Prefix of the hooks: `<testid>-filters`, `-filters-count`, `-filters-panel`, `-filter-<key>`… */
  testid: string;
}>();

const values = defineModel<FilterValues>({ required: true });

const open = ref(false);

const keysOf = (filter: FilterSpec): readonly string[] => (filter.kind === 'range' ? filter.keys : [filter.key]);
const inUse = (key: string): boolean => (values.value[key] ?? '').trim() !== '';

/** Filters in use; a range counts once. */
const count = computed(() => props.filters.filter((f) => keysOf(f).some(inUse)).length);

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

/** The names of the choices made in the pickers, to show them (the value is an id). */
const picked = ref<Record<string, string>>({});

function pick(key: string, value: string, label: string): void {
  picked.value = { ...picked.value, [key]: label };
  set(key, value);
}
</script>

<template>
  <ion-button
    class="staff-filters__button"
    fill="outline"
    color="medium"
    :data-testid="`${testid}-filters`"
    :aria-label="count ? $t('staff.filters.count', { n: count }) : $t('staff.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('staff.filters.button') }}
    <ion-badge
      v-if="count"
      class="staff-filters__count"
      color="primary"
      :data-testid="`${testid}-filters-count`"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('staff.filters.title')"
    :testid="`${testid}-filters-panel`"
    @submit="open = false"
  >
    <div class="staff-filters__fields">
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
          :value="values[filter.key] ?? ''"
          :debounce="300"
          :clear-input="true"
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
          @ion-change="set(filter.key, $event.detail.value)"
        >
          <ion-select-option value="">
            {{ $t('staff.filters.any') }}
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
          :label="filter.label"
          :value="values[filter.key] ?? ''"
          :display="values[filter.key] ? (picked[filter.key] ?? values[filter.key]) : ''"
          :none-label="$t('staff.filters.any')"
          :load="filter.load"
          @update:value="(value: string, label: string) => pick(filter.key, value, label)"
        />
        <div
          v-else
          class="staff-filters__range"
        >
          <ion-input
            v-for="(key, index) in filter.keys"
            :key="key"
            :data-testid="`${testid}-filter-${key}`"
            :label="`${filter.label} · ${index === 0 ? $t('staff.filters.from') : $t('staff.filters.to')}`"
            label-placement="floating"
            fill="outline"
            mode="md"
            :type="filter.type ?? 'number'"
            :inputmode="filter.type === 'date' ? undefined : 'numeric'"
            :value="values[key] ?? ''"
            :debounce="300"
            @ion-input="set(key, $event.detail.value)"
          />
        </div>
      </template>
    </div>
    <template #footer>
      <ion-button
        fill="clear"
        class="staff-filters__clear"
        :data-testid="`${testid}-filters-clear`"
        @click="clear"
      >
        {{ $t('staff.filters.clear') }}
      </ion-button>
      <ion-button
        :data-testid="`${testid}-filters-done`"
        @click="open = false"
      >
        {{ $t('staff.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
/* Boxed like the table's own toolbar selects (38 px, radius 10). */
.staff-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
.staff-filters__count {
  margin-inline-start: 0.4rem;
}
.staff-filters__fields {
  display: grid;
  gap: 14px;
}
.staff-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.staff-filters__clear {
  --color: var(--ion-text-color);
}
</style>
