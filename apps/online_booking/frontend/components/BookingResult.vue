<script setup lang="ts">
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import type { ApiError } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { dayOf, formatDay, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { STATUS_TONE } from '../../../appointment/frontend/lib/states';
import { useLocale, useT } from '../composables/useT';
import type { BookedOut, PublicBookingOut } from '../operations';
import CancelDialog from './CancelDialog.vue';

const props = withDefaults(defineProps<{
  booked: BookedOut | null;
  seen: PublicBookingOut | null;
  pending: boolean;
  error: string;
  token: string;
  cancelError?: ApiError | null;
  link?: string;
  personal?: boolean;
}>(), { cancelError: null, link: '', personal: false });
const emit = defineEmits<{
  view: [];
  cancel: [reason: string];
  again: [];
}>();
const t = useT();
const locale = useLocale();
const cancelUntil = computed(() => {
  const until = props.seen?.cancel_until;
  return until ? `${formatDay(dayOf(until), locale.value)} · ${formatTime(timeOf(until), locale.value)}` : '';
});
const startsAt = computed(() => {
  const start = props.seen?.start;
  return start ? `${formatDay(dayOf(start), locale.value)} · ${formatTime(timeOf(start), locale.value)}` : '';
});

// Cancelling asks first, as on her link's page; the confirmation has done its job once the booking shows as cancelled.
// It opens without the last refusal: only what this attempt is refused with shows in it.
const asking = ref(false);
const refusal = ref<ApiError | null>(null);
watch(() => props.cancelError, (error) => {
  refusal.value = error;
});
watch(() => props.seen?.status, (status) => {
  if (status === 'cancelled') asking.value = false;
});

function ask(): void {
  refusal.value = null;
  asking.value = true;
}
</script>

<template>
  <InlineFeedback
    v-if="booked"
    tone="success"
    data-testid="ob-preview-booked"
    :heading="$t('online_booking.preview.booked', { number: booked.number })"
  >
    {{ booked.message }}
  </InlineFeedback>
  <p
    v-if="booked"
    class="ob-result__token"
    data-testid="ob-preview-token"
  >
    {{ $t('online_booking.preview.link') }}:
    <a
      v-if="link"
      :href="link"
    >{{ link }}</a>
    <code v-else>{{ booked.token }}</code>
  </p>
  <div
    v-if="seen"
    data-testid="ob-preview-status"
  >
    <StatusPill
      :label="t(`online_booking.bookings.status.${seen.status}`)"
      :tone="STATUS_TONE[seen.status]"
    />
    <p><strong>{{ seen.number }}</strong></p>
    <p>{{ seen.service_names }}</p>
    <p>{{ startsAt }}</p>
    <p v-if="seen.staff_name">
      {{ seen.staff_name }}
    </p>
    <p v-if="seen.status !== 'cancelled'">
      {{ seen.can_cancel ? $t('online_booking.preview.cancelUntil', { when: cancelUntil }) : $t('online_booking.preview.noCancel') }}
    </p>
    <p v-if="seen.cancellation_policy">
      {{ $t('online_booking.preview.policy') }}: {{ seen.cancellation_policy }}
    </p>
  </div>
  <InlineFeedback
    v-if="seen?.status === 'cancelled'"
    tone="neutral"
    data-testid="ob-personal-cancelled"
    role="status"
  >
    {{ $t('online_booking.door.cancelled') }}
  </InlineFeedback>
  <div class="ob-result__actions">
    <ion-button
      v-if="booked && !personal"
      data-testid="ob-preview-view"
      fill="outline"
      :disabled="pending"
      @click="emit('view')"
    >
      {{ $t('online_booking.preview.view') }}
    </ion-button>
    <ion-button
      v-if="seen?.can_cancel || (booked !== null && !personal)"
      data-testid="ob-preview-cancel"
      color="danger"
      fill="outline"
      :disabled="pending || (seen !== null && !seen.can_cancel)"
      @click="ask"
    >
      {{ $t('online_booking.preview.cancel') }}
    </ion-button>
    <ion-button
      v-if="booked && !personal"
      data-testid="ob-preview-again"
      fill="clear"
      @click="emit('again')"
    >
      {{ $t('online_booking.preview.again') }}
    </ion-button>
  </div>
  <InlineFeedback
    v-if="error"
    tone="danger"
    data-testid="ob-preview-link-error"
  >
    {{ error }}
  </InlineFeedback>
  <CancelDialog
    v-model:open="asking"
    :booking="seen ?? booked"
    :token="token"
    :pending="pending"
    :error="refusal"
    @confirm="emit('cancel', $event)"
  />
</template>

<style scoped>
.ob-result__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ob-result__token {
  overflow-wrap: anywhere;
}
</style>
