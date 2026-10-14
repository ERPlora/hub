<script setup lang="ts">
// «Erase personal data» of a card (CUSTOMER-F16), the product's two-step panel on the card: what is
// erased and that it cannot be undone, the reason for the audit (optional), then the danger button.
// The server erases the person (and the duplicates merged into it) keeping the sales; the card then
// leaves every list, so the page goes back to the list.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput } from '@ionic/vue';
import { ref } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';

const props = defineProps<{ customer: { id: string; name: string } }>();
const emit = defineEmits<{ erased: []; cancel: [] }>();

const { t } = useCustomerI18n();
const { run: erase, pending, error } = useCommand('customer.customer.erase');
const reason = ref('');

async function confirm(): Promise<void> {
  try {
    await erase({ id: props.customer.id, reason: reason.value.trim() });
  } catch {
    return; // `error` holds it: the panel shows it.
  }
  void toastSuccess(t('customer.erase.done'));
  emit('erased');
}
</script>

<template>
  <section
    class="customer-panel"
    data-testid="customer-erase"
  >
    <h3>{{ $t('customer.erase.title') }}</h3>
    <p>{{ $t('customer.erase.message', { name: customer.name }) }}</p>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="customer-erase-error"
    >
      {{ error.message }}
    </InlineFeedback>
    <ion-input
      v-model="reason"
      data-testid="customer-erase-reason"
      :label="$t('customer.erase.reason')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :maxlength="500"
    />
    <div class="customer-panel__actions">
      <ion-button
        size="small"
        color="danger"
        data-testid="customer-erase-submit"
        :disabled="pending"
        @click="confirm"
      >
        {{ $t('customer.erase.submit') }}
      </ion-button>
      <ion-button
        size="small"
        fill="outline"
        data-testid="customer-erase-cancel"
        :disabled="pending"
        @click="emit('cancel')"
      >
        {{ $t('customer.common.cancel') }}
      </ion-button>
    </div>
  </section>
</template>

<style scoped>
.customer-panel {
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: var(--ep-radius-sm, 10px);
  padding: 0.75rem 1rem;
  margin: 0 0 1rem;
  background: var(--ep-surface-2, var(--ion-color-step-50, rgba(24, 24, 27, 0.04)));
}

.customer-panel h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-panel__actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.75rem;
  flex-wrap: wrap;
}
</style>
