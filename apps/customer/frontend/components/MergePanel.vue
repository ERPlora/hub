<script setup lang="ts">
// «Merge with…» of a card (CUSTOMER-F13), the product's panel on the card: the open card always
// STAYS (choosing the survivor would be one more decision at the counter; opening the other card
// covers that case). Pick the duplicate (never itself), read what happens to it, «Merge»: one call,
// all or nothing. The card's live result then shows what it gained; the list loses the duplicate.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { ref } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomerRow } from '../operations';
import CustomerPicker from './CustomerPicker.vue';

const props = defineProps<{ customer: { id: string; name: string } }>();
const emit = defineEmits<{ done: [] }>();

const { t } = useCustomerI18n();
const { run: merge, pending, error } = useCommand('customer.customer.merge');

const term = ref('');
const target = ref<CustomerRow | null>(null);

function pick(row: CustomerRow): void {
  error.value = null;
  target.value = row;
}

async function confirm(): Promise<void> {
  const absorbed = target.value;
  if (!absorbed) return;
  try {
    await merge({ id: props.customer.id, absorbed_id: absorbed.id });
  } catch {
    return; // `error` holds it: the panel shows it.
  }
  void toastSuccess(t('customer.merge.done', { name: absorbed.name }));
  emit('done');
}
</script>

<template>
  <section
    class="customer-panel"
    data-testid="customer-merge"
  >
    <h3>{{ $t('customer.merge.title') }}</h3>
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="customer-merge-error"
    >
      {{ error.message }}
    </InlineFeedback>
    <div
      v-if="target"
      data-testid="customer-merge-confirm"
    >
      <p>{{ $t('customer.merge.confirm', { absorbed: target.name, surviving: customer.name }) }}</p>
      <div class="customer-panel__actions">
        <ion-button
          size="small"
          color="danger"
          data-testid="customer-merge-submit"
          :disabled="pending"
          @click="confirm"
        >
          {{ $t('customer.merge.submit') }}
        </ion-button>
        <ion-button
          size="small"
          fill="outline"
          data-testid="customer-merge-change"
          :disabled="pending"
          @click="target = null"
        >
          {{ $t('customer.merge.change') }}
        </ion-button>
        <ion-button
          size="small"
          fill="clear"
          data-testid="customer-merge-cancel"
          :disabled="pending"
          @click="emit('done')"
        >
          {{ $t('customer.common.cancel') }}
        </ion-button>
      </div>
    </div>
    <template v-else>
      <p>{{ $t('customer.merge.hint', { name: customer.name }) }}</p>
      <CustomerPicker
        v-model:term="term"
        :exclude="[customer.id]"
        :placeholder="$t('customer.merge.search')"
        :empty-message="$t('customer.merge.noCandidates')"
        @pick="pick"
      />
      <div class="customer-panel__actions">
        <ion-button
          size="small"
          fill="outline"
          data-testid="customer-merge-cancel"
          @click="emit('done')"
        >
          {{ $t('customer.common.cancel') }}
        </ion-button>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* The product's `.panel`: a bordered, tinted box on the card. */
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
  margin-top: 0.5rem;
  flex-wrap: wrap;
}
</style>
