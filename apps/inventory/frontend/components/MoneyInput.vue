<script setup lang="ts">
// A money field of the inventory forms (price, cost, a reception's unit cost; WORKBOOK INVENTORY-F01):
// what a person types or pastes («2,20», «1.234,56», «2,20 €»), in the business's currency, rewritten in the page format when
// they leave it (once the business has answered: until then, as typed). It holds the text; the form reads the cents
// with `parseMoney` when it saves. What is not an amount says so under the field once the person leaves it (or
// `showError`, after a save attempt); the server's message for the field wins.
import { IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { formatMoney, useBusinessMoney } from '../lib/format';
import { normaliseMoneyText, parseMoney } from '../lib/money';

const props = withDefaults(
  defineProps<{ label: string; testid: string; errorText?: string; showError?: boolean; disabled?: boolean }>(),
  { errorText: undefined, showError: false, disabled: false },
);
const text = defineModel<string>({ required: true });

const { t, locale } = useT();
const business = useBusinessMoney();
const left = ref(false);

/** Why the text is not an amount, in the page language; `''` when it is one (or empty). */
const readError = computed(() => {
  const read = parseMoney(text.value, business.value);
  if (read.ok) return '';
  if (read.reason === 'not_amount') return t('inventory.common.noAmount');
  return t('inventory.common.ambiguousAmount', {
    typed: text.value.trim(),
    grouped: formatMoney(read.grouped, locale.value, business.value),
    decimal: formatMoney(read.decimal, locale.value, business.value),
  });
});

const message = computed(() => props.errorText || ((left.value || props.showError) && readError.value) || undefined);

function onBlur(): void {
  left.value = true;
  // Until the business answers, its decimals are unknown: what was typed stays, never «150» made «150.00».
  if (!business.value) return;
  const normalised = normaliseMoneyText(text.value, locale.value, business.value);
  if (normalised !== text.value) text.value = normalised;
}
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
    :error-text="message"
    :class="{ 'ion-invalid': !!message, 'ion-touched': !!message }"
    @update:model-value="text = $event === null || $event === undefined ? '' : String($event)"
    @ion-blur="onBlur"
  />
</template>
