<script setup lang="ts">
// The amount field of «New payment» (WORKBOOK PAYMENT-F02): what a person types or pastes («22,50», «1.234,56», «22,50 €»), rewritten in the page
// format when they leave it. It holds the text; the form reads the cents with `parseMoney` when it
// saves. What is not an amount says so under the field once the person leaves it (or `showError`,
// after a save attempt); the server's message for the field wins.
import { IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMoney } from '../lib/format';
import { normaliseMoneyText, parseMoney } from '../lib/money';

const props = withDefaults(
  defineProps<{ label: string; testid: string; errorText?: string; helperText?: string; showError?: boolean; disabled?: boolean }>(),
  { errorText: undefined, helperText: undefined, showError: false, disabled: false },
);
const text = defineModel<string>({ required: true });

const t = useT();
const locale = useLocale();
const left = ref(false);

/** Why the text is not an amount, in the page language; `''` when it is one (or empty). */
const readError = computed(() => {
  const read = parseMoney(text.value);
  if (read.ok) return '';
  if (read.reason === 'not_amount') return t('payment.money.notAmount');
  if (read.reason === 'negative') return t('payment.money.negative');
  return t('payment.money.ambiguous', {
    typed: text.value.trim(),
    grouped: formatMoney(read.grouped, locale.value),
    decimal: formatMoney(read.decimal, locale.value),
  });
});

const message = computed(() => props.errorText || ((left.value || props.showError) && readError.value) || undefined);

function onBlur(): void {
  left.value = true;
  const normalised = normaliseMoneyText(text.value, locale.value);
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
    :helper-text="helperText"
    :error-text="message"
    :class="{ 'ion-invalid': !!message, 'ion-touched': !!message }"
    @update:model-value="text = $event === null || $event === undefined ? '' : String($event)"
    @ion-blur="onBlur"
  />
</template>
