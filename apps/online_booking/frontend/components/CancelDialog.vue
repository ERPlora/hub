<script setup lang="ts">
// ONLINE_BOOKING-F05: cancelling (or declining) a booking asks first (the market: Fresha, Timely, Phorest),
// naming whose booking and when, with an optional reason kept in the appointment's history. «Cancel the
// booking» cancels it (its time becomes free); «Keep it» leaves it. A refusal stays in the dialog.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { dayOf, formatDay, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { useLocale, useT } from '../composables/useT';
import type { BookingRow } from '../operations';

const props = defineProps<{ booking: BookingRow | null }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const cancel = useCommand('online_booking.booking.cancel');
const reason = ref('');

watch(open, (isOpen) => {
  if (!isOpen) return;
  reason.value = '';
  cancel.error.value = null;
});

const message = computed(() => {
  const item = props.booking;
  if (!item) return '';
  const when = `${formatDay(dayOf(item.start), locale.value)} · ${formatTime(timeOf(item.start), locale.value)}`;
  const customer = item.customer_name || t('online_booking.bookings.erasedCustomer');
  return t('online_booking.bookings.cancel.message', { customer, when });
});

async function confirm(): Promise<void> {
  if (!props.booking) return;
  try {
    await cancel.run({ id: props.booking.id, reason: reason.value.trim() });
  } catch {
    return; // The dialog says why.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="ob-cancel"
    size="sm"
    role="alertdialog"
    :title="$t('online_booking.bookings.cancel.title')"
    :submit-label="$t('online_booking.bookings.cancel.confirm')"
    :cancel-label="$t('online_booking.bookings.cancel.keep')"
    submit-color="danger"
    :pending="cancel.pending.value"
    :error="cancel.error.value"
    @submit="confirm"
  >
    <p>{{ message }}</p>
    <ion-textarea
      data-testid="ob-cancel-reason"
      :value="reason"
      :label="$t('online_booking.bookings.cancel.reason')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :maxlength="500"
      @ion-input="reason = String($event.detail.value ?? '')"
    />
  </FormModal>
</template>
