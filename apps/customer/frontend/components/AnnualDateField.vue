<script setup lang="ts">
// A birthday or an anniversary of the card's form (CUSTOMER-F01, F04): the day, the month and, only if it is known,
// the year, typed in three number fields, as forms ask a date a person knows (no calendar to scroll back decades),
// in the order the page language writes a day. The model is the day the card keeps (lib/dates.ts); a part still
// missing goes up as typed, so the server's refusal comes back under the three fields.
import { InlineFeedback } from '@erplora/ui/components';
import { IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import FieldGroup from '../../../../base/frontend/components/FieldGroup.vue';
import { type AnnualDatePart, type AnnualDateParts, annualDate, annualDateOrder, annualDateParts } from '../lib/dates';
import { useCustomerI18n } from '../lib/useCustomerI18n';

const model = defineModel<string>({ required: true });
const props = defineProps<{
  label: string;
  testid: string;
  errorText?: string;
}>();

const { t, locale } = useCustomerI18n();

const MAX_LENGTH: Record<AnnualDatePart, number> = { day: 2, month: 2, year: 4 };

const parts = ref<AnnualDateParts>(annualDateParts(model.value));
// Another change of the card (a save, a live update) brings its day; what the person is typing stays.
watch(model, (value) => {
  if (value !== annualDate(parts.value)) parts.value = annualDateParts(value);
});

const order = computed(() => annualDateOrder(locale.value));

function set(part: AnnualDatePart, value: unknown): void {
  parts.value = { ...parts.value, [part]: String(value ?? '') };
  model.value = annualDate(parts.value);
}

const invalid = computed(() => ({ 'ion-invalid': !!props.errorText, 'ion-touched': !!props.errorText }));
</script>

<template>
  <FieldGroup
    class="annual-date"
    :data-testid="testid"
  >
    <legend class="annual-date__legend">
      {{ label }}
    </legend>
    <div class="annual-date__parts">
      <ion-input
        v-for="part in order"
        :key="part"
        :class="['annual-date__part', `annual-date__part--${part}`, invalid]"
        :data-testid="`${testid}-${part}`"
        :model-value="parts[part]"
        :label="t(`customer.form.${part}`)"
        label-placement="floating"
        fill="outline"
        mode="md"
        type="text"
        inputmode="numeric"
        :maxlength="MAX_LENGTH[part]"
        :helper-text="part === 'year' ? t('customer.form.optional') : undefined"
        @update:model-value="set(part, $event)"
      />
    </div>
    <InlineFeedback
      v-if="errorText"
      tone="danger"
      role="alert"
    >
      {{ errorText }}
    </InlineFeedback>
  </FieldGroup>
</template>

<style scoped>
.annual-date__legend {
  padding: 0 0 0.35rem;
  font-size: 0.85rem;
  color: var(--ion-color-medium);
}

/* The three parts in one row, the year a little wider; each takes the row's height of its own (the year's helper). */
.annual-date__parts {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
}

.annual-date__part {
  flex: 1 1 3.5rem;
  min-width: 0;
}

.annual-date__part--year {
  flex: 1.4 1 4.5rem;
}
</style>
