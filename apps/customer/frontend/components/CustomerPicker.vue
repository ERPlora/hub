<script setup lang="ts">
// The customer picker (WORKBOOK «La búsqueda de texto de la lista»: F13, F17, F18): a search box
// over the first 20 cards by name, followed live; typing searches as the list does (name, phone
// however typed, email, tax id, company). It tells «searching», «no matches», «down» (with Retry,
// the text kept) and «no permission» apart, as the product's till search did (customers#18). A tap
// hands the card up (`pick`); `v-model:term` lets the parent offer «+ New customer «…»». A screen reader
// reads the search box by its hint, in the person's language, never Ionic's English «search text».
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonSearchbar } from '@ionic/vue';
import { computed, useTemplateRef } from 'vue';

import { formatPhone } from '../lib/phoneDisplay';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import { useSearchbarName } from '../lib/useSearchbarName';
import type { CustomerRow } from '../operations';

const props = withDefaults(
  defineProps<{
    /** Cards never offered (the open card, in «Merge with…»). */
    exclude?: string[];
    /** The card already chosen: marked. */
    selectedId?: string;
    /** What «no matches» says instead of the default. */
    emptyMessage?: string;
    /** Hint of the search box instead of the default. */
    placeholder?: string;
  }>(),
  { exclude: () => [], selectedId: undefined, emptyMessage: undefined, placeholder: undefined },
);

const term = defineModel<string>('term', { default: '' });
const emit = defineEmits<{ pick: [customer: CustomerRow] }>();

const { t } = useCustomerI18n();
const hint = computed(() => props.placeholder ?? t('customer.picker.search'));
useSearchbarName(useTemplateRef('bar'), () => hint.value);

const FIRST = 20;
const { data, status, error, refresh } = useLive('customer.customer.list', () => ({
  ...(term.value.trim() ? { search: term.value.trim() } : {}),
  limit: FIRST,
  sort: 'name' as const,
}));

const rows = computed(() => (data.value?.rows ?? []).filter((row) => !props.exclude.includes(row.id)));
const forbidden = computed(() => error.value?.code === 'permission_denied');
const failed = computed(() => status.value === 'error' && error.value?.code !== 'app_inactive');
const searching = computed(() => status.value === 'loading' && !failed.value);

function onInput(event: Event): void {
  term.value = String((event.target as HTMLInputElement | null)?.value ?? '');
}
</script>

<template>
  <div class="customer-picker">
    <ion-searchbar
      ref="bar"
      class="ion-no-border customer-picker__search"
      data-testid="customer-picker-search"
      :value="term"
      :placeholder="hint"
      :aria-label="$t('customer.picker.searchLabel')"
      :debounce="250"
      @ion-input="onInput"
    />
    <InlineFeedback
      v-if="failed"
      tone="danger"
      data-testid="customer-picker-error"
    >
      {{ forbidden ? $t('customer.picker.noPermission') : `${$t('customer.picker.loadError')}: ${error?.message}` }}
      <template
        v-if="!forbidden"
        #actions
      >
        <ion-button
          size="small"
          fill="outline"
          data-testid="customer-picker-retry"
          @click="refresh()"
        >
          {{ $t('customer.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <p
      v-else-if="searching && !rows.length"
      class="customer-picker__state"
      data-testid="customer-picker-searching"
      role="status"
    >
      {{ $t('customer.common.loading') }}
    </p>
    <p
      v-else-if="data && !rows.length"
      class="customer-picker__state"
      data-testid="customer-picker-empty"
    >
      {{ emptyMessage ?? (term.trim() ? $t('customer.picker.noResults') : $t('customer.picker.noCustomers')) }}
    </p>
    <ion-list
      v-if="rows.length"
      class="customer-picker__list"
      lines="none"
    >
      <ion-item
        v-for="row in rows"
        :key="row.id"
        button
        :detail="false"
        :class="{ 'customer-picker__item--selected': row.id === selectedId }"
        :data-testid="`customer-picker-result-${row.id}`"
        @click="emit('pick', row)"
      >
        <ion-label>
          <h3>{{ row.name }}</h3>
          <p v-if="row.phone || row.email">
            {{ row.phone ? formatPhone(row.phone) : row.email }}
          </p>
        </ion-label>
        <HubIcon
          v-if="row.id === selectedId"
          slot="end"
          class="customer-picker__mark"
          name="ion:checkmark-outline"
          data-testid="customer-picker-selected"
        />
      </ion-item>
    </ion-list>
  </div>
</template>

<style scoped>
.customer-picker__search {
  padding-inline: 0;
}

.customer-picker__list {
  background: transparent;
  max-height: 18rem;
  overflow: auto;
}

.customer-picker__list ion-item {
  --background: transparent;
  border-radius: var(--ep-radius-sm, 10px);
}

.customer-picker__item--selected {
  --background: color-mix(in srgb, var(--ion-color-primary, #0091ce) 16%, transparent);
}

.customer-picker__mark {
  color: var(--ion-color-primary, #0054e9);
}

.customer-picker__state {
  text-align: center;
  padding: 1.25rem 0;
  opacity: 0.7;
  margin: 0;
}
</style>
