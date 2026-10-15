<script setup lang="ts">
// «Cancel record» (VERIFACTU-F30; the old module had it only by the assistant or the API): «Cancel the record of
// <number>», the note that this declares to the AEAT an invoice issued BY ERROR (a refund or a correction is a
// rectifying invoice in Invoicing), «Reason» (required) and «Cancel the record». It runs
// `verifactu.record.cancel`; the cancellation record goes out with the next pass. A refusal is read inside the
// window, in the server's words.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';

const props = defineProps<{ record: { id: string; invoice_number: string } | null }>();
const open = defineModel<boolean>('open', { required: true });

const t = useT();
const command = useCommand('verifactu.record.cancel');
const reason = shallowRef('');
const missing = shallowRef(false);

watch(
  open,
  (now) => {
    if (!now) return;
    reason.value = '';
    missing.value = false;
    command.error.value = null;
  },
  { immediate: true },
);

const error = computed<FormModalError | null>(() =>
  missing.value ? { message: t('verifactu.detail.reasonRequired') } : refusal(command.error.value, t('verifactu.detail.actionFailed')),
);

async function cancel(): Promise<void> {
  const record = props.record;
  if (!record || command.pending.value) return;
  const text = reason.value.trim();
  missing.value = !text;
  if (!text) return;
  try {
    await command.run({ record_id: record.id, reason: text });
  } catch {
    return; // The window shows `command.error`.
  }
  void toastSuccess(t('verifactu.detail.cancelDone', { number: record.invoice_number }));
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="verifactu-cancel"
    role="alertdialog"
    submit-color="danger"
    :title="$t('verifactu.detail.cancelTitle', { number: record?.invoice_number ?? '' })"
    :submit-label="$t('verifactu.detail.cancelSubmit')"
    :cancel-label="$t('verifactu.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="cancel"
  >
    <p
      class="verifactu-cancel__note"
      data-testid="verifactu-cancel-note"
    >
      {{ $t('verifactu.detail.cancelNote') }}
    </p>
    <ion-textarea
      data-testid="verifactu-cancel-reason"
      :label="$t('verifactu.detail.cancelReason')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :maxlength="500"
      :auto-grow="true"
      :value="reason"
      @ion-input="reason = String($event.detail.value ?? '')"
    />
  </FormModal>
</template>

<style scoped>
.verifactu-cancel__note {
  margin: 0 0 0.75rem;
  color: var(--ion-color-medium, #8a8577);
  font-size: 0.9rem;
}
</style>
