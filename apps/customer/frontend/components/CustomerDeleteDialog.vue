<script setup lang="ts">
// «Delete» of a card (CUSTOMER-F07), from the list or the card: the shared ConfirmDialog asks
// «Delete customer» — «Delete {name}? …» (the product asked in an alert dialog too); confirmed, the
// card is deleted keeping its data, sales and history, and «Customer {name} deleted» is said. The
// dialog stays open while it runs and shows a refusal. `v-model:customer` holds the card asked about.
import { ConfirmDialog } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';

interface Target {
  id: string;
  name: string;
}

const customer = defineModel<Target | null>('customer', { default: null });
const emit = defineEmits<{ deleted: [id: string] }>();

const { t } = useCustomerI18n();
const { run: remove, pending, error } = useCommand('customer.customer.delete');

/** The name stays while the dialog closes. */
const shown = ref<Target | null>(customer.value);
watch(customer, (now) => {
  if (now) {
    shown.value = now;
    error.value = null;
  }
});

const open = computed({
  get: () => customer.value !== null,
  set: (value: boolean) => {
    if (!value) customer.value = null;
  },
});

async function confirm(): Promise<void> {
  const target = customer.value;
  if (!target) return;
  try {
    await remove({ id: target.id });
  } catch {
    return; // `error` holds it: the dialog shows it.
  }
  customer.value = null;
  emit('deleted', target.id);
  void toastSuccess(t('customer.delete.done', { name: target.name }));
}
</script>

<template>
  <ConfirmDialog
    v-model:open="open"
    testid="customer-delete-confirm"
    tone="danger"
    :title="$t('customer.delete.title')"
    :message="$t('customer.delete.message', { name: shown?.name ?? '' })"
    :confirm-label="$t('customer.delete.confirm')"
    confirm-icon="ion:trash-outline"
    :pending="pending"
    :error="error"
    @confirm="confirm"
  />
</template>
