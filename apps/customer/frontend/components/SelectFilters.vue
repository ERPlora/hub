<script lang="ts">
/** A closed-list filter: its query parameter, its label and its choices («Any» is added). */
export interface SelectFilterSpec {
  key: string;
  label: string;
  options: readonly { value: string; label: string }[];
}
</script>

<script setup lang="ts">
// The closed-list filters of the Groups, Tags and Fields tables (WORKBOOK «Pantallas»): the product's
// table filter panel as a «Filters» button with the count in use, opening one select per filter in
// the shared FormModal (UI-REQUESTS.md asks the DataTable for column filters). A change applies at
// once; «Clear» drops them all; «Done» closes.
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

const values = defineModel<Record<string, string>>({ required: true });
defineProps<{ filters: readonly SelectFilterSpec[]; testid: string }>();

const open = ref(false);
const count = computed(() => Object.values(values.value).filter((v) => v !== '').length);

function set(key: string, value: unknown): void {
  const text = value === null || value === undefined ? '' : String(value);
  const next = { ...values.value };
  if (text) next[key] = text;
  else delete next[key];
  values.value = next;
}
</script>

<template>
  <ion-button
    class="customer-select-filters__button"
    size="small"
    fill="outline"
    color="medium"
    :data-testid="`${testid}-filters`"
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
      class="customer-select-filters__count"
      color="primary"
      :data-testid="`${testid}-filters-count`"
    >
      {{ count }}
    </ion-badge>
  </ion-button>

  <FormModal
    v-model:open="open"
    size="sm"
    :testid="`${testid}-filters-panel`"
    :title="$t('customer.filters.title')"
    @submit="open = false"
  >
    <div class="customer-select-filters__fields">
      <ion-select
        v-for="filter in filters"
        :key="filter.key"
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
          {{ $t('customer.filters.any') }}
        </ion-select-option>
        <ion-select-option
          v-for="option in filter.options"
          :key="option.value"
          :value="option.value"
        >
          {{ option.label }}
        </ion-select-option>
      </ion-select>
    </div>
    <template #footer>
      <ion-button
        fill="clear"
        :data-testid="`${testid}-filters-clear`"
        :disabled="!count"
        @click="values = {}"
      >
        {{ $t('customer.filters.clear') }}
      </ion-button>
      <ion-button
        :data-testid="`${testid}-filters-done`"
        @click="open = false"
      >
        {{ $t('customer.filters.done') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.customer-select-filters__button {
  margin: 0;
}

.customer-select-filters__count {
  margin-inline-start: 0.4rem;
}

.customer-select-filters__fields {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
</style>
