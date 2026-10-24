<script setup lang="ts">
// «Add» of the customer list (CUSTOMER-F01): the card's form in the shared FormModal, the closest
// to the product's side panel of the table (UI-REQUESTS.md asks for that panel). One call with the
// whole card; only the name is required. Saved: the dialog closes and the live list and figures
// paint the new card by themselves. Refused: it stays open with what was typed; a 422 goes under
// its field (F11: a phone that is not one of its country), anything else on top of the form.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { computed, ref, useTemplateRef, watch } from 'vue';

import { refusalFields, refusalOutsideFields } from '../lib/apiErrors';
import { blankCustomer, createInput, ESSENTIAL_FIELDS, MORE_FIELDS } from '../lib/customerForm';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomerDetailOut } from '../operations';
import CustomerForm from './CustomerForm.vue';

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ created: [customer: CustomerDetailOut] }>();

const { t } = useCustomerI18n();
const { run: create, pending, error } = useCommand('customer.customer.create');

const form = ref(blankCustomer());
const SHOWN = [...ESSENTIAL_FIELDS, ...MORE_FIELDS];
const errors = computed(() => refusalFields(error.value));
const cardForm = useTemplateRef<InstanceType<typeof CustomerForm>>('cardForm');
const failure = computed(() => {
  const message = refusalOutsideFields(error.value, SHOWN);
  return message ? { message } : null;
});

// Every opening starts from a blank card and no refusal.
watch(open, (isOpen) => {
  if (!isOpen) return;
  form.value = blankCustomer();
  error.value = null;
});

async function save(): Promise<void> {
  // A date the browser could not read would go as "" (no date): told under its field, not sent.
  if (cardForm.value && !cardForm.value.readable()) return;
  let customer: CustomerDetailOut;
  try {
    customer = await create(createInput(form.value));
  } catch {
    return; // `error` holds it: the form paints it.
  }
  open.value = false;
  emit('created', customer);
  void toastSuccess(t('customer.create.created', { name: customer.name }));
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="customer-create"
    :title="$t('customer.create.title')"
    :pending="pending"
    :error="failure"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <CustomerForm
      ref="cardForm"
      v-model="form"
      mode="create"
      :errors="errors"
    />
  </FormModal>
</template>
