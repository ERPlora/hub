<script setup lang="ts">
// TAX-F07 (change a rate from a date): a rule is never edited; its rate changes by ending
// it the day before the new one starts (Oracle E-Business Tax, Dynamics 365, SAP). This dialog asks
// for that last day (the old `ion-alert` with a date) and sends `tax.rule.end`. A refusal (an end
// before the start, an overlap with another active rule) stays here, under the date.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput } from '@ionic/vue';
import { ref, watch } from 'vue';

import type { RuleOut } from '../operations';

const props = defineProps<{
  /** The rule being ended; `null` while no row asked. */
  rule: RuleOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const validTo = ref('');
const { run, error, pending } = useCommand('tax.rule.end');

// Each opening starts from the end the rule already has (empty for an open-ended one).
watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    validTo.value = props.rule?.valid_to ?? '';
    error.value = null;
  },
  { immediate: true },
);

const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  const rule = props.rule;
  if (!rule || !validTo.value) return;
  try {
    await run({ id: rule.id, valid_to: validTo.value });
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="tax-rule-end"
    size="sm"
    :title="$t('tax.rules.end.title')"
    :submit-label="$t('tax.rules.end.submit')"
    submit-icon="ion:calendar-outline"
    :pending="pending"
    :error="error"
    :submit-disabled="!validTo"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <p
        class="tax-rule-end__message"
        data-testid="tax-rule-end-message"
      >
        {{ $t('tax.rules.end.message') }}
      </p>
      <ion-input
        data-testid="tax-rule-end-valid_to"
        type="date"
        :value="validTo"
        :label="$t('tax.rules.end.field')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="fieldErrors.valid_to"
        :class="invalid(fieldErrors.valid_to)"
        @ion-input="validTo = String($event.detail.value ?? '')"
      />
    </template>
  </FormModal>
</template>

<style scoped>
.tax-rule-end__message {
  margin: 0 0 16px;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 14px;
  line-height: 1.45;
}
</style>
