<script setup lang="ts">
// The payment-method picker of Sales: «Give it back through» in a refund (the list's «Payment» filter is
// the table funnel's lookup, `lib/salesFilters.ts`). A
// read-only outlined field opening a window with a searchbar and the list, the pattern Ionic recommends
// for a list that may grow (an `ion-select` has no search). The list is the server's
// (`sale.payment_method.list`, searched there, a short page), live while the picker is on screen. A
// method shows as the reader reads it (`display_name`); the value is its stored name (`valueKey="name"`:
// a filter compares the sale's stored method) or its id (`valueKey="id"`: a refund's destination).
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
import { computed, ref, shallowRef } from 'vue';

import type { PaymentMethodOut } from '../../operations';

/** A short page: a business has a handful of methods; the search finds the rest. */
const PAGE = 20;

const props = withDefaults(
  defineProps<{
    valueKey: 'name' | 'id';
    label: string;
    /** «Any» as the first option (a filter): its value is ''. */
    anyLabel?: string;
    errorText?: string;
    /** Hooks: `<testid>` (the field), `-modal`, `-search`, `-option` (`data-value`), `-loading`, `-empty`, `-error`, `-close`. */
    testid: string;
  }>(),
  { anyLabel: undefined, errorText: undefined },
);

const value = defineModel<string>({ required: true });

const open = ref(false);
const typed = shallowRef('');
/** The name of the chosen method, for when a later answer no longer lists it. */
const chosenLabel = shallowRef<string>();

const { data, status, error } = useLive('sale.payment_method.list', () => ({
  ...(typed.value.trim() ? { search: typed.value.trim() } : {}),
  limit: PAGE,
}));

interface Option {
  value: string;
  label: string;
}

const valueOf = (method: PaymentMethodOut): string => (props.valueKey === 'id' ? method.id : method.name);

const options = computed<Option[]>(() => {
  const methods = (data.value?.rows ?? []).map((method) => ({ value: valueOf(method), label: method.display_name }));
  return props.anyLabel === undefined ? methods : [{ value: '', label: props.anyLabel }, ...methods];
});

const shown = computed(() => {
  if (!value.value) return '';
  return options.value.find((option) => option.value === value.value)?.label ?? chosenLabel.value ?? value.value;
});

function show(): void {
  typed.value = '';
  open.value = true;
}

function onSearch(event: CustomEvent<{ value?: string | null }>): void {
  typed.value = event.detail.value ?? '';
}

function choose(option: Option): void {
  chosenLabel.value = option.value ? option.label : undefined;
  value.value = option.value;
  open.value = false;
}

const invalid = computed(() => ({ 'ion-invalid': !!props.errorText, 'ion-touched': !!props.errorText }));
</script>

<template>
  <ion-input
    class="sale-method-picker"
    :data-testid="testid"
    :value="shown"
    :label="label"
    :placeholder="anyLabel"
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
  <ion-modal
    :is-open="open"
    :data-testid="`${testid}-modal`"
    :aria-label="label"
    @did-dismiss="open = false"
  >
    <ion-header class="ion-no-border">
      <ion-toolbar>
        <ion-title>{{ label }}</ion-title>
        <ion-buttons slot="end">
          <ion-button
            :aria-label="$t('sale.sales.picker.close')"
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
          :placeholder="$t('sale.sales.picker.search')"
          :debounce="250"
          @ion-input="onSearch"
        />
      </ion-toolbar>
    </ion-header>
    <ion-content>
      <p
        v-if="error"
        class="ion-padding ion-text-center sale-method-picker__error"
        :data-testid="`${testid}-error`"
      >
        {{ $t('sale.sales.picker.error') }} {{ error.message }}
      </p>
      <div
        v-else-if="!data && status !== 'live'"
        class="ion-text-center ion-padding"
      >
        <ion-spinner :data-testid="`${testid}-loading`" />
      </div>
      <ion-list v-else-if="options.length && (data?.rows.length ?? 0) > 0">
        <ion-item
          v-for="option in options"
          :key="option.value"
          button
          :detail="false"
          :data-testid="`${testid}-option`"
          :data-value="option.value"
          :class="{ 'sale-method-picker__option--chosen': option.value === value }"
          @click="choose(option)"
        >
          <span class="sale-method-picker__label">{{ option.label }}</span>
          <HubIcon
            v-if="option.value === value"
            slot="end"
            name="ion:checkmark-outline"
          />
        </ion-item>
      </ion-list>
      <p
        v-else
        class="ion-padding ion-text-center sale-method-picker__empty"
        :data-testid="`${testid}-empty`"
      >
        {{ $t('sale.sales.picker.empty') }}
      </p>
    </ion-content>
  </ion-modal>
</template>

<style scoped>
.sale-method-picker {
  cursor: pointer;
}
.sale-method-picker__empty {
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.sale-method-picker__error {
  color: var(--ion-color-danger, #c5000f);
}
.sale-method-picker__label {
  flex: 1 1 auto;
  padding: 10px 0;
}
.sale-method-picker__option--chosen {
  font-weight: 600;
}
</style>
