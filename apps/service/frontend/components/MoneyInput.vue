<script setup lang="ts">
// A money field of the service forms (a price, a closed price, a professional's own price; WORKBOOK
// SERVICE-F01): what a person types or pastes («22,50», «1.234,56», «22,50 zł»), in the business's currency
// (service-business-currency), rewritten in the page format when they leave it (once the business has answered:
// until then, as typed). It holds the text; the form reads the minor units with `parseMoney` when it saves. What
// is not an amount says so under the field once the person leaves it (or `showError`, after a save attempt); the
// server's message for the field wins.
import { IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMoney, useBusinessMoney } from '../lib/format';
import { normaliseMoneyText, parseMoney } from '../lib/money';

const props = withDefaults(
  defineProps<{ label: string; testid: string; errorText?: string; helperText?: string; showError?: boolean; disabled?: boolean }>(),
  { errorText: undefined, helperText: undefined, showError: false, disabled: false },
);
const text = defineModel<string>({ required: true });

const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const left = ref(false);

/** Why the text is not an amount, in the page language; `''` when it is one (or empty). */
const readError = computed(() => {
  const read = parseMoney(text.value, money.value);
  if (read.ok) return '';
  if (read.reason === 'not_amount') return t('service.money.notAmount');
  if (read.reason === 'negative') return t('service.money.negative');
  return t('service.money.ambiguous', {
    typed: text.value.trim(),
    grouped: formatMoney(read.grouped, locale.value, money.value),
    decimal: formatMoney(read.decimal, locale.value, money.value),
  });
});

const message = computed(() => props.errorText || ((left.value || props.showError) && readError.value) || undefined);

function onBlur(): void {
  left.value = true;
  // Until the business answers, its decimals are unknown: what was typed stays, never «150» made «150.00».
  if (!money.value) return;
  const normalised = normaliseMoneyText(text.value, locale.value, money.value);
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
