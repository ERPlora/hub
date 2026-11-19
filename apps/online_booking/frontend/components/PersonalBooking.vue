<script setup lang="ts">
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, inject, onMounted, ref } from 'vue';

import { PUBLIC_DOOR } from '../lib/door';
import type { PublicBookingOut } from '../operations';
import BookingResult from './BookingResult.vue';
import CancelDialog from './CancelDialog.vue';
import PublicBookingHeader from './PublicBookingHeader.vue';

const props = defineProps<{ token: string }>();
const door = inject(PUBLIC_DOOR);
if (!door) throw new Error('PersonalBooking needs the public door');
const api = door.api;

const seen = ref<PublicBookingOut | null>(null);
const loading = ref(true);
const loadError = ref<ApiError | null>(null);
const dialogOpen = ref(false);
const cancelling = ref(false);
const cancelError = ref<ApiError | null>(null);
const notFound = computed(() => loadError.value?.code === 'online_booking.booking_not_found');

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = null;
  try {
    seen.value = await api.call('online_booking.public.booking', { token: props.token });
  } catch (failure) {
    seen.value = null;
    loadError.value = failure instanceof ApiError ? failure : new ApiError(0, 'client_error', String(failure));
  } finally {
    loading.value = false;
  }
}

function action(op: 'online_booking.public.booking' | 'online_booking.public.cancel'): void {
  if (op === 'online_booking.public.cancel') {
    cancelError.value = null;
    dialogOpen.value = true;
  }
}

async function cancel(reason: string): Promise<void> {
  cancelling.value = true;
  cancelError.value = null;
  try {
    seen.value = await api.call('online_booking.public.cancel', { token: props.token, reason });
    dialogOpen.value = false;
  } catch (failure) {
    cancelError.value = failure instanceof ApiError ? failure : new ApiError(0, 'client_error', String(failure));
  } finally {
    cancelling.value = false;
  }
}

onMounted(load);
</script>

<template>
  <AppPage
    :title="$t('online_booking.door.title')"
    content-layout="detail"
  >
    <div data-testid="ob-personal">
      <PublicBookingHeader
        v-if="seen"
        :info="seen"
      />
      <p
        v-if="loading"
        data-testid="ob-personal-loading"
        role="status"
      >
        <ion-spinner name="crescent" />
        {{ $t('online_booking.door.loadingBooking') }}
      </p>
      <InlineFeedback
        v-else-if="loadError"
        :tone="notFound ? 'warning' : 'danger'"
        data-testid="ob-personal-error"
        role="alert"
      >
        {{ loadError.message }}
        <template
          v-if="!notFound"
          #actions
        >
          <ion-button
            fill="clear"
            @click="load"
          >
            {{ $t('online_booking.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <BookingResult
        v-else-if="seen"
        :booked="null"
        :seen="seen"
        :pending="cancelling"
        error=""
        personal
        @action="action"
      />
      <CancelDialog
        v-model:open="dialogOpen"
        :booking="seen"
        :token="token"
        :pending="cancelling"
        :error="cancelError"
        @confirm="cancel"
      />
    </div>
  </AppPage>
</template>
