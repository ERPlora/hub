<script lang="ts">
/** One choice of a closed-list filter. */
export interface FilterOption {
  value: string;
  label: string;
}

/** A column filter: a text fragment, a choice of a closed list (plus «Any») or a from–to range of dates. */
export type FilterSpec =
  | { kind: 'text'; key: string; label: string }
  | { kind: 'select'; key: string; label: string; options: readonly FilterOption[] }
  | { kind: 'range'; key: string; label: string; keys: readonly [string, string] };

/** Filter values by the query parameter they fill; a filter not in use is absent. */
export type FilterValues = Readonly<Record<string, string>>;
</script>

<script setup lang="ts">
// The column filters of a schedule list: the old table's funnel button, with the count of filters in
// use, opening its filters (here a dialog: FormModal) with one control per filter. A change applies at
// once (the page asks the server again); «Clear» drops them all; «Done» closes. The shared DataTable's
// own filters take one day, not a range of dates (UI-REQUESTS.md): each schedule list puts this in its
// `filters` slot.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

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

</script>

<template>
  <ion-button
    class="schedule-filters__button"
    fill="outline"
    color="medium"
    :data-testid="`${testid}-filters`"
    :aria-label="count ? $t('schedule.filters.count', { n: count }) : $t('schedule.filters.button')"
    @click="open = true"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('schedule.filters.button') }}
    <ion-badge
      v-if="count"
      class="schedule-filters__count"
      color="primary"
      :data-testid="`${testid}-filters-count`"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :title="$t('schedule.filters.title')"
    :testid="`${testid}-filters-panel`"
    @submit="open = false"
  >
    <div class="schedule-filters__fields">
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
            {{ $t('schedule.filters.any') }}
          </ion-select-option>
          <ion-select-option
            v-for="option in filter.options"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </ion-select-option>
        </ion-select>
        <div
          v-else
          class="schedule-filters__range"
        >
          <ion-input
            v-for="(key, index) in filter.keys"
            :key="key"
            :data-testid="`${testid}-filter-${key}`"
            :label="`${filter.label} · ${index === 0 ? $t('schedule.filters.from') : $t('schedule.filters.to')}`"
            label-placement="floating"
            fill="outline"
            mode="md"
            type="date"
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
        class="schedule-filters__clear"
        :data-testid="`${testid}-filters-clear`"
        @click="clear"
      >
        {{ $t('schedule.filters.clear') }}
      </ion-button>
      <ion-button
        :data-testid="`${testid}-filters-done`"
        @click="open = false"
      >
        {{ $t('schedule.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
/* Boxed like the table's own toolbar selects (38 px, radius 10). */
.schedule-filters__button {
  min-height: 38px;
  margin: 0;
  --border-radius: 10px;
  --padding-start: 0.7rem;
  --padding-end: 0.7rem;
  font-size: 13px;
  text-transform: none;
}
.schedule-filters__count {
  margin-inline-start: 0.4rem;
}
.schedule-filters__fields {
  display: grid;
  gap: 14px;
}
.schedule-filters__range {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.schedule-filters__clear {
  --color: var(--ion-text-color);
}
</style>
