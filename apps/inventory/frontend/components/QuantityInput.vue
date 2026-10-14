<script setup lang="ts">
// A quantity field of the inventory (initial stock, threshold, received, counted, written off;
// WORKBOOK INVENTORY-F26): it says the unit and its step («In kg, in steps of 0.001») and accepts
// «2,5» or «0.532». It holds the text; the form reads the decimal with `readQuantity` when it saves.
// What is not a quantity says so once the person leaves the field (or `showError`); whether it fits
// the unit's step is the server's to say, and the server's message for the field wins.
import { IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { formatQuantity } from '../lib/format';
import { readQuantity } from '../lib/quantity';

const props = withDefaults(
  defineProps<{
    label: string;
    testid: string;
    /** Code of the unit («kg»). */
    unit?: string;
    /** The unit's step («0.001»). */
    step?: string;
    errorText?: string;
    showError?: boolean;
    disabled?: boolean;
  }>(),
  { unit: undefined, step: undefined, errorText: undefined, showError: false, disabled: false },
);
const text = defineModel<string>({ required: true });

const { t, locale } = useT();
const left = ref(false);

const hint = computed(() =>
  props.unit && props.step ? t('inventory.common.stepHint', { unit: props.unit, step: formatQuantity(props.step, locale.value) }) : undefined,
);
const readError = computed(() => (readQuantity(text.value).ok ? '' : t('inventory.common.noQuantity')));
const message = computed(() => props.errorText || ((left.value || props.showError) && readError.value) || undefined);
</script>

<template>
  <ion-input
    :data-testid="testid"
    :model-value="text"
    type="text"
    inputmode="decimal"
    :label="label"
    label-placement="floating"
    fill="outline"
    mode="md"
    :disabled="disabled"
    :helper-text="hint"
    :error-text="message"
    :class="{ 'ion-invalid': !!message, 'ion-touched': !!message }"
    @update:model-value="text = $event === null || $event === undefined ? '' : String($event)"
    @ion-blur="left = true"
  />
</template>
