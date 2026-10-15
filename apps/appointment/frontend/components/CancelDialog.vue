<script setup lang="ts">
// APPOINTMENT-F05: cancelling from the agenda asks first (the market: Fresha, Timely, Phorest), naming
// whose appointment and when, with an optional reason kept in its history. «Cancel the appointment»
// cancels it (its time becomes free); «Keep it» leaves it. A refusal (already cancelled, charged…) stays
// in the dialog.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { dayOf, formatDay, formatTime, timeOf } from '../lib/clock';
import { customerLabel } from '../lib/states';
import type { AppointmentRow } from '../operations';

const props = defineProps<{ appointment: AppointmentRow | null }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const cancel = useCommand('appointment.appointment.cancel');
const reason = ref('');

watch(open, (isOpen) => {
  if (!isOpen) return;
  reason.value = '';
  cancel.error.value = null;
});

const message = computed(() => {
  const item = props.appointment;
  if (!item) return '';
  const when = `${formatDay(dayOf(item.start), locale.value)} · ${formatTime(timeOf(item.start), locale.value)}`;
  return t('appointment.cancelDialog.message', { customer: customerLabel(item, t), when });
});

async function confirm(): Promise<void> {
  if (!props.appointment) return;
  try {
    await cancel.run({ id: props.appointment.id, reason: reason.value.trim() });
  } catch {
    return; // The dialog says why.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="appointment-cancel"
    size="sm"
    role="alertdialog"
    :title="$t('appointment.cancelDialog.title')"
    :submit-label="$t('appointment.cancelDialog.confirm')"
    :cancel-label="$t('appointment.cancelDialog.keep')"
    submit-color="danger"
    :pending="cancel.pending.value"
    :error="cancel.error.value"
    @submit="confirm"
  >
    <p>{{ message }}</p>
    <ion-textarea
      data-testid="appointment-cancel-reason"
      :value="reason"
      :label="$t('appointment.cancelDialog.reason')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :maxlength="500"
      @ion-input="reason = String($event.detail.value ?? '')"
    />
  </FormModal>
</template>
