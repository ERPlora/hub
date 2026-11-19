<script setup lang="ts">
import { InlineFeedback, StatusPill } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import { dayOf, formatDay, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { STATUS_TONE } from '../../../appointment/frontend/lib/states';
import { useLocale, useT } from '../composables/useT';
import type { BookedOut, PublicBookingOut } from '../operations';

const props = withDefaults(defineProps<{
  booked: BookedOut | null;
  seen: PublicBookingOut | null;
  pending: boolean;
  error: string;
  link?: string;
  personal?: boolean;
}>(), { link: '', personal: false });
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
const startsAt = computed(() => {
  const start = props.seen?.start;
  return start ? `${formatDay(dayOf(start), locale.value)} · ${formatTime(timeOf(start), locale.value)}` : '';
});
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
      @click="emit('action', 'online_booking.public.booking')"
    >
      {{ $t('online_booking.preview.view') }}
    </ion-button>
    <ion-button
      v-if="seen?.can_cancel || (booked !== null && !personal)"
      data-testid="ob-preview-cancel"
      color="danger"
      fill="outline"
      :disabled="pending || (seen !== null && !seen.can_cancel)"
      @click="emit('action', 'online_booking.public.cancel')"
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
