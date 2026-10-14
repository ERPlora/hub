<script setup lang="ts">
// The Refund window (SALE-F31): «Refund sale <number>» around the refund body (RefundForm), which only
// exists, and only reads what can go back, while the window is open: every opening is a new attempt
// with its own key. Its button is the body's «Refund <amount>»; Enter in a field asks the same. A
// refund recorded closes the window (the row and the figures follow by themselves, live).
import { FormModal } from '@erplora/ui/components';
import { useTemplateRef } from 'vue';

import type { SaleRow } from '../../operations';
import RefundForm from './RefundForm.vue';

defineProps<{ sale: Pick<SaleRow, 'id' | 'number'> | null }>();

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ refunded: [] }>();

const form = useTemplateRef<InstanceType<typeof RefundForm>>('form');

function refunded(): void {
  open.value = false;
  emit('refunded');
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="sale-refund"
    role="alertdialog"
    :title="$t('sale.refund.title', { number: sale?.number ?? '' })"
    @submit="form?.confirm()"
  >
    <RefundForm
      v-if="open && sale"
      ref="form"
      :sale-id="sale.id"
      @refunded="refunded"
    />
    <template #footer>
      <span />
    </template>
  </FormModal>
</template>
