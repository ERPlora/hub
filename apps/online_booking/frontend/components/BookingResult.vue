<script setup lang="ts">
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { dayOf, formatDay, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { useLocale, useT } from '../composables/useT';
import type { BookedOut, PublicBookingOut } from '../operations';

const props = defineProps<{
  booked: BookedOut;
  seen: PublicBookingOut | null;
  pending: boolean;
  error: string;
}>();
const emit = defineEmits<{
  action: [op: 'online_booking.public.booking' | 'online_booking.public.cancel'];
  again: [];
}>();
const t = useT();
const locale = useLocale();
const cancelUntil = computed(() => {
  const until = props.seen?.cancel_until;
  return until ? `${formatDay(dayOf(until), locale.value)} · ${formatTime(timeOf(until), locale.value)}` : '';
});
</script>

<template>
  <InlineFeedback
    tone="success"
    data-testid="ob-preview-booked"
    :heading="$t('online_booking.preview.booked', { number: booked.number })"
  >
    {{ booked.message }}
  </InlineFeedback>
  <p
    class="ob-result__token"
    data-testid="ob-preview-token"
  >
    {{ $t('online_booking.preview.link') }}: <code>{{ booked.token }}</code>
  </p>
  <div class="ob-result__actions">
    <ion-button
      data-testid="ob-preview-view"
      fill="outline"
      :disabled="pending"
      @click="emit('action', 'online_booking.public.booking')"
    >
      {{ $t('online_booking.preview.view') }}
    </ion-button>
    <ion-button
      data-testid="ob-preview-cancel"
      color="danger"
      fill="outline"
      :disabled="pending || (seen !== null && !seen.can_cancel)"
      @click="emit('action', 'online_booking.public.cancel')"
    >
      {{ $t('online_booking.preview.cancel') }}
    </ion-button>
    <ion-button
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
  <div
    v-if="seen"
    data-testid="ob-preview-status"
  >
    <p>
      <strong>{{ t(`online_booking.bookings.status.${seen.status}`) }}</strong>
      · {{ seen.number }} · {{ seen.service_names }} · {{ seen.staff_name }}
    </p>
    <p>
      {{ seen.can_cancel ? $t('online_booking.preview.cancelUntil', { when: cancelUntil }) : $t('online_booking.preview.noCancel') }}
    </p>
    <p v-if="seen.cancellation_policy">
      {{ $t('online_booking.preview.policy') }}: {{ seen.cancellation_policy }}
    </p>
  </div>
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
