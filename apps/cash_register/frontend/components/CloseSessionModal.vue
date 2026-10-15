<script setup lang="ts">
// «Close session · S-…» (CASH_REGISTER-F09): the window around its body (CloseSessionForm), which only
// exists, and only reads the session, its counts and the open checks, while the window is open. Its
// buttons are the body's («Close session» / «Close anyway», «Cancel»); a closed session closes the window
// (the row and «Open session» follow by themselves, live).
import { FormModal } from '@erplora/ui/components';
import { useTemplateRef } from 'vue';

import CloseSessionForm from './CloseSessionForm.vue';

defineProps<{ session: { id: string; number: string } | null }>();

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ closed: [] }>();

const form = useTemplateRef<InstanceType<typeof CloseSessionForm>>('form');

function closed(): void {
  open.value = false;
  emit('closed');
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="cash-register-close"
    role="alertdialog"
    :title="$t('cash_register.close.title', { number: session?.number ?? '' })"
    @submit="form?.confirm()"
  >
    <CloseSessionForm
      v-if="open && session"
      ref="form"
      :session="session"
      @closed="closed"
      @cancel="open = false"
    />
    <template #footer>
      <span />
    </template>
  </FormModal>
</template>
