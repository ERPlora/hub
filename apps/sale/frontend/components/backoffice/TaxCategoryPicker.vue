<script setup lang="ts">
// «VAT charged» of a department (SALE-F35): a choice among the business's tax categories, however many
// there are, so it never loads them all. An outlined read-only field opens a modal with a searchbar over
// the live `tax.category.list` (50 at a time, searched on the server, the pattern Ionic recommends for
// long lists); each choice reads «Name · rate» with the rate the server says it charges today. Under the
// field, the old screen's notices: no category to choose, or a failed read with «Retry».
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonInput,
  IonItem,
  IonList,
  IonModal,
  IonSearchbar,
  IonSpinner,
  IonTitle,
  IonToolbar,
} from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { taxLabel } from './taxLabel';

/** How many choices one answer brings: the rest are reached by typing. */
const PAGE = 50;
/** The longest search `tax.category.list` takes. */
const MAX_SEARCH = 120;

const props = withDefaults(
  defineProps<{
    /** The label of the chosen category when it is not among the choices on screen (an edit). */
    chosenLabel?: string;
    errorText?: string;
    /** Hooks: `<testid>` (the field), `-modal`, `-search`, `-option` (`data-value`), `-loading`,
     *  `-empty`, `-more`, `-none`, `-error`, `-retry`, `-close`. */
    testid: string;
  }>(),
  { chosenLabel: undefined, errorText: undefined },
);

/** The chosen category's key. */
const value = defineModel<string>({ required: true });
/** `v-model:empty`: the business has no tax category to choose (its form cannot be saved). */
const empty = defineModel<boolean>('empty', { default: false });

const t = useT();
const locale = useLocale();

const open = ref(false);
const typed = ref('');
/** The label of the option picked here, for when a later answer no longer lists it. */
const picked = ref<string>();

const search = computed(() => typed.value.trim().slice(0, MAX_SEARCH));
const { data, status, error, refresh } = useLive('tax.category.list', () => ({
  ...(search.value ? { search: search.value } : {}),
  sort: 'display_name' as const,
  dir: 'asc' as const,
  limit: PAGE,
}));

const options = computed(() =>
  (data.value?.rows ?? []).map((row) => ({
    value: row.key,
    label: taxLabel(row.display_name || row.name, row.rate_pct, locale.value, row.key),
  })),
);

const shown = computed(() => {
  if (!value.value) return '';
  return options.value.find((option) => option.value === value.value)?.label ?? picked.value ?? props.chosenLabel ?? value.value;
});

/** The business has no category at all (an answer to no search with nothing in it). */
const none = computed(() => status.value === 'live' && !search.value && data.value?.total === 0);
const more = computed(() => (data.value && data.value.total > data.value.rows.length ? { shown: data.value.rows.length, total: data.value.total } : null));
const failed = computed(() => status.value === 'error' && !!error.value);
// Only an answer to no search says whether the business has any category at all.
watch(
  data,
  (now) => {
    if (now && !search.value) empty.value = now.total === 0;
  },
  { immediate: true },
);

/** «Retrying…» from the tap on «Retry» until the server answers again (a result or another error). */
const retrying = ref(false);
watch([data, error], () => (retrying.value = false));
function retry(): void {
  retrying.value = true;
  refresh();
}

function show(): void {
  typed.value = '';
  open.value = true;
}

function choose(option: { value: string; label: string }): void {
  picked.value = option.label;
  value.value = option.value;
  open.value = false;
}

const invalid = computed(() => ({ 'ion-invalid': !!props.errorText, 'ion-touched': !!props.errorText }));
</script>

<template>
  <div class="sale-tax-picker">
    <ion-input
      class="sale-tax-picker__field"
      :data-testid="testid"
      :value="shown"
      :label="t('sale.departments.columns.taxCategory')"
      :placeholder="t('sale.departments.form.taxPlaceholder')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :readonly="true"
      :error-text="errorText"
      :class="invalid"
      @click="show"
      @keydown.enter.prevent="show"
    >
      <HubIcon
        slot="end"
        name="ion:chevron-down-outline"
        aria-hidden="true"
      />
    </ion-input>
    <InlineFeedback
      v-if="failed"
      tone="danger"
      :data-testid="`${testid}-error`"
      :heading="t('sale.departments.taxLoadFailed')"
    >
      {{ error?.message }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          :data-testid="`${testid}-retry`"
          :disabled="retrying"
          @click="retry"
        >
          {{ retrying ? t('sale.departments.taxRetrying') : t('sale.departments.taxRetry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <InlineFeedback
      v-else-if="none"
      tone="warning"
      :data-testid="`${testid}-none`"
    >
      {{ t('sale.departments.noTaxCategories') }}
    </InlineFeedback>

    <ion-modal
      :is-open="open"
      :data-testid="`${testid}-modal`"
      :aria-label="t('sale.departments.columns.taxCategory')"
      @did-dismiss="open = false"
    >
      <ion-header class="ion-no-border">
        <ion-toolbar>
          <ion-title>{{ t('sale.departments.columns.taxCategory') }}</ion-title>
          <ion-buttons slot="end">
            <ion-button
              :aria-label="t('sale.departments.picker.close')"
              :data-testid="`${testid}-close`"
              @click="open = false"
            >
              <HubIcon
                slot="icon-only"
                name="ion:close-outline"
              />
            </ion-button>
          </ion-buttons>
        </ion-toolbar>
        <ion-toolbar>
          <ion-searchbar
            :data-testid="`${testid}-search`"
            :value="typed"
            :placeholder="t('sale.departments.picker.search')"
            :debounce="250"
            @ion-input="typed = String($event.detail.value ?? '')"
          />
        </ion-toolbar>
      </ion-header>
      <ion-content>
        <div
          v-if="status === 'loading' && !options.length"
          class="ion-text-center ion-padding"
        >
          <ion-spinner :data-testid="`${testid}-loading`" />
        </div>
        <InlineFeedback
          v-else-if="failed"
          class="ion-margin"
          tone="danger"
          :heading="t('sale.departments.taxLoadFailed')"
        >
          {{ error?.message }}
        </InlineFeedback>
        <ion-list v-else-if="options.length">
          <ion-item
            v-for="option in options"
            :key="option.value"
            button
            :detail="false"
            :data-testid="`${testid}-option`"
            :data-value="option.value"
            :class="{ 'sale-tax-picker__option--chosen': option.value === value }"
            @click="choose(option)"
          >
            <span class="sale-tax-picker__label">{{ option.label }}</span>
            <HubIcon
              v-if="option.value === value"
              slot="end"
              name="ion:checkmark-outline"
            />
          </ion-item>
        </ion-list>
        <p
          v-else-if="none"
          class="ion-padding ion-text-center sale-tax-picker__muted"
        >
          {{ t('sale.departments.noTaxCategories') }}
        </p>
        <p
          v-else
          class="ion-padding ion-text-center sale-tax-picker__muted"
          :data-testid="`${testid}-empty`"
        >
          {{ t('sale.departments.picker.noResults') }}
        </p>
        <p
          v-if="more && options.length"
          class="ion-padding ion-text-center sale-tax-picker__muted"
          :data-testid="`${testid}-more`"
        >
          {{ t('sale.departments.picker.more', more) }}
        </p>
      </ion-content>
    </ion-modal>
  </div>
</template>

<style scoped>
.sale-tax-picker {
  display: grid;
  gap: 8px;
}
.sale-tax-picker__field {
  cursor: pointer;
}
.sale-tax-picker__muted {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.sale-tax-picker__label {
  flex: 1 1 auto;
  padding: 10px 0;
}
.sale-tax-picker__option--chosen {
  font-weight: 600;
}
</style>
