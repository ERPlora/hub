<script setup lang="ts">
// The preview of the public booking page, on the dev server only (routes.ts; WORKBOOK «Vista previa de la
// reserva»): the customer's flow with the same public operations the page of base (`/p/<slug>/book`, Django
// templates) will call in-process — services, a professional or «No preference», a day and a free time, name
// and mobile, book; then the booking seen and cancelled with the personal link. One-shot calls of the API
// client (what is public is not followed live). Never part of a production build.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonInput, IonSelect, IonSelectOption, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, onMounted, ref, watch } from 'vue';

import { dayOf, formatDay, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { formatMoney } from '../../../appointment/frontend/lib/format';
import { useLocale, useT } from '../composables/useT';
import type {
  BookedOut,
  PageOut,
  ProfessionalOut,
  PublicBookingOut,
  PublicServiceOut,
  PublicSlotOut,
} from '../operations';

/** The services the preview lists (the server's cap on a page). */
const SERVICE_WINDOW = 100;

const client = useLiveClient();
const t = useT();
const locale = useLocale();

const asError = (failure: unknown): ApiError =>
  failure instanceof ApiError ? failure : new ApiError(0, 'client_error', failure instanceof Error ? failure.message : String(failure));

// The page and its services
const info = ref<PageOut | null>(null);
const services = ref<PublicServiceOut[]>([]);
/** The services have arrived: only then does an empty list mean «none booked online». */
const servicesLoaded = ref(false);
const loadError = ref<ApiError | null>(null);

onMounted(async () => {
  try {
    info.value = await client.api.call('online_booking.public.page', {});
    services.value = (await client.api.call('online_booking.public.services', { limit: SERVICE_WINDOW })).rows;
    servicesLoaded.value = true;
  } catch (failure) {
    loadError.value = asError(failure);
  }
});

function priceAndLength(service: PublicServiceOut): string {
  const parts = [
    service.price === null ? '' : formatMoney(service.price, locale.value),
    service.duration_minutes === null ? '' : t('online_booking.preview.minutes', { n: service.duration_minutes }),
  ];
  return parts.filter(Boolean).join(' · ');
}

// What the customer picks
const chosen = ref<string[]>([]);
const staff = ref('');
const day = ref('');
const start = ref('');
const name = ref('');
const phone = ref('');
const email = ref('');
const notes = ref('');

function pick(id: string, on: boolean): void {
  chosen.value = on ? [...chosen.value.filter((item) => item !== id), id] : chosen.value.filter((item) => item !== id);
}

/** Who does every chosen service. */
const professionals = computed<ProfessionalOut[]>(() => {
  const picked = services.value.filter((service) => chosen.value.includes(service.id));
  if (!picked.length) return [];
  return picked[0].professionals.filter((person) => picked.every((service) => service.professionals.some((other) => other.id === person.id)));
});
watch(professionals, (now) => {
  if (staff.value && !now.some((person) => person.id === staff.value)) staff.value = '';
});

// The free times
const slots = ref<PublicSlotOut[] | null>(null);
const slotsLoading = ref(false);
const slotsError = ref<ApiError | null>(null);

watch([chosen, staff, day], async () => {
  start.value = '';
  slots.value = null;
  slotsError.value = null;
  if (!chosen.value.length || !day.value) return;
  slotsLoading.value = true;
  try {
    const answer = await client.api.call('online_booking.public.slots', {
      service_ids: chosen.value,
      date: day.value,
      ...(staff.value ? { staff_id: staff.value } : {}),
    });
    slots.value = answer.slots;
  } catch (failure) {
    slotsError.value = asError(failure);
  } finally {
    slotsLoading.value = false;
  }
});

const wallOf = (moment: string): string => `${dayOf(moment)}T${timeOf(moment)}`;

// Booking
const booking = ref(false);
const bookError = ref<ApiError | null>(null);
const booked = ref<BookedOut | null>(null);
const fieldErrors = computed<Readonly<Record<string, string>>>(() => bookError.value?.fields ?? {});
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const ready = computed(() => !!start.value && !!name.value.trim() && !!phone.value.trim() && !booking.value);

async function book(): Promise<void> {
  if (!ready.value) return;
  booking.value = true;
  bookError.value = null;
  try {
    booked.value = await client.api.call('online_booking.public.book', {
      service_ids: chosen.value,
      ...(staff.value ? { staff_id: staff.value } : {}),
      start: start.value,
      name: name.value.trim(),
      phone: phone.value.trim(),
      email: email.value.trim(),
      notes: notes.value.trim(),
    });
  } catch (failure) {
    bookError.value = asError(failure);
  } finally {
    booking.value = false;
  }
}

// The personal link
const seen = ref<PublicBookingOut | null>(null);
const linkError = ref<ApiError | null>(null);
const linkPending = ref(false);

async function byLink(op: 'online_booking.public.booking' | 'online_booking.public.cancel'): Promise<void> {
  if (!booked.value) return;
  linkPending.value = true;
  linkError.value = null;
  try {
    seen.value = await client.api.call(op, { token: booked.value.token });
  } catch (failure) {
    linkError.value = asError(failure);
  } finally {
    linkPending.value = false;
  }
}

const cancelUntil = computed(() => {
  const until = seen.value?.cancel_until;
  return until ? `${formatDay(dayOf(until), locale.value)} · ${formatTime(timeOf(until), locale.value)}` : '';
});

function again(): void {
  booked.value = null;
  seen.value = null;
  start.value = '';
  name.value = phone.value = email.value = notes.value = '';
  chosen.value = [];
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <AppPage
    :title="$t('online_booking.preview.title')"
    content-layout="detail"
  >
    <div
      class="ob-preview"
      data-testid="ob-preview"
    >
      <h2>{{ $t('online_booking.preview.title') }}</h2>
      <p class="ob-preview__help">
        {{ $t('online_booking.preview.intro') }}
      </p>
      <InlineFeedback
        v-if="loadError"
        tone="warning"
        data-testid="ob-preview-error"
        :heading="$t('online_booking.preview.loadError')"
      >
        {{ loadError.message }}
      </InlineFeedback>
      <p
        v-else-if="!info"
        class="ob-preview__help"
      >
        <ion-spinner name="crescent" />
        {{ $t('online_booking.preview.loading') }}
      </p>
      <section
        v-else
        class="ob-preview__page"
        :style="{ '--ob-accent': info.primary_color }"
      >
        <h3 data-testid="ob-preview-title">
          {{ info.title }}
        </h3>
        <p v-if="info.welcome_message">
          {{ info.welcome_message }}
        </p>

        <template v-if="!booked">
          <h4>{{ $t('online_booking.preview.services') }}</h4>
          <ion-checkbox
            v-for="service in services"
            :key="service.id"
            :data-testid="`ob-preview-service-${service.id}`"
            label-placement="end"
            justify="start"
            :checked="chosen.includes(service.id)"
            @ion-change="pick(service.id, $event.detail.checked)"
          >
            {{ service.name }}
            <small v-if="priceAndLength(service)">{{ priceAndLength(service) }}</small>
          </ion-checkbox>
          <p
            v-if="servicesLoaded && !services.length"
            data-testid="ob-preview-no-services"
            class="ob-preview__help"
          >
            {{ $t('online_booking.preview.noServices') }}
          </p>

          <ion-select
            v-if="info.allow_staff_selection"
            data-testid="ob-preview-staff"
            :value="staff"
            :label="$t('online_booking.preview.professional')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="staff = text($event.detail.value)"
          >
            <ion-select-option value="">
              {{ $t('online_booking.preview.anyone') }}
            </ion-select-option>
            <ion-select-option
              v-for="person in professionals"
              :key="person.id"
              :value="person.id"
            >
              {{ person.name }}
            </ion-select-option>
          </ion-select>

          <ion-input
            data-testid="ob-preview-day"
            type="date"
            :value="day"
            :label="$t('online_booking.preview.day')"
            label-placement="floating"
            fill="outline"
            mode="md"
            @ion-change="day = text($event.detail.value)"
          />

          <template v-if="chosen.length && day">
            <h4>{{ $t('online_booking.preview.times') }}</h4>
            <p
              v-if="slotsLoading"
              class="ob-preview__help"
            >
              {{ $t('online_booking.preview.loadingTimes') }}
            </p>
            <InlineFeedback
              v-else-if="slotsError"
              tone="danger"
              data-testid="ob-preview-slots-error"
            >
              {{ slotsError.message }}
            </InlineFeedback>
            <p
              v-else-if="slots && !slots.length"
              data-testid="ob-preview-no-times"
            >
              {{ $t('online_booking.preview.noTimes') }}
            </p>
            <div
              v-else-if="slots"
              class="ob-preview__times"
            >
              <ion-button
                v-for="slot in slots"
                :key="slot.start"
                :data-testid="`ob-preview-time-${timeOf(slot.start)}`"
                size="small"
                :fill="start === wallOf(slot.start) ? 'solid' : 'outline'"
                @click="start = wallOf(slot.start)"
              >
                {{ formatTime(timeOf(slot.start), locale) }}
              </ion-button>
            </div>
          </template>

          <ion-input
            data-testid="ob-preview-name"
            :value="name"
            :label="$t('online_booking.preview.name')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="200"
            :error-text="fieldErrors.name"
            :class="invalid(fieldErrors.name)"
            @ion-input="name = text($event.detail.value)"
          />
          <ion-input
            data-testid="ob-preview-phone"
            type="tel"
            :value="phone"
            :label="$t('online_booking.preview.phone')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="30"
            :error-text="fieldErrors.phone"
            :class="invalid(fieldErrors.phone)"
            @ion-input="phone = text($event.detail.value)"
          />
          <ion-input
            data-testid="ob-preview-email"
            type="email"
            :value="email"
            :label="`${$t('online_booking.preview.email')}${info.require_email ? ' *' : ''}`"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.email"
            :class="invalid(fieldErrors.email)"
            @ion-input="email = text($event.detail.value)"
          />
          <ion-textarea
            v-if="info.allow_notes"
            data-testid="ob-preview-notes"
            :value="notes"
            :label="$t('online_booking.preview.notes')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="500"
            :error-text="fieldErrors.notes"
            :class="invalid(fieldErrors.notes)"
            @ion-input="notes = text($event.detail.value)"
          />
          <InlineFeedback
            v-if="bookError"
            tone="danger"
            data-testid="ob-preview-form-error"
          >
            {{ bookError.message }}
          </InlineFeedback>
          <ion-button
            data-testid="ob-preview-book"
            :disabled="!ready"
            @click="book"
          >
            {{ $t('online_booking.preview.book') }}
          </ion-button>
        </template>

        <template v-else>
          <InlineFeedback
            tone="success"
            data-testid="ob-preview-booked"
            :heading="$t('online_booking.preview.booked', { number: booked.number })"
          >
            {{ booked.message }}
          </InlineFeedback>
          <p data-testid="ob-preview-token">
            {{ $t('online_booking.preview.link') }}: <code>{{ booked.token }}</code>
          </p>
          <div class="ob-preview__times">
            <ion-button
              data-testid="ob-preview-view"
              fill="outline"
              :disabled="linkPending"
              @click="byLink('online_booking.public.booking')"
            >
              {{ $t('online_booking.preview.view') }}
            </ion-button>
            <ion-button
              data-testid="ob-preview-cancel"
              color="danger"
              fill="outline"
              :disabled="linkPending || (seen !== null && !seen.can_cancel)"
              @click="byLink('online_booking.public.cancel')"
            >
              {{ $t('online_booking.preview.cancel') }}
            </ion-button>
            <ion-button
              data-testid="ob-preview-again"
              fill="clear"
              @click="again"
            >
              {{ $t('online_booking.preview.again') }}
            </ion-button>
          </div>
          <InlineFeedback
            v-if="linkError"
            tone="danger"
            data-testid="ob-preview-link-error"
          >
            {{ linkError.message }}
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
      </section>
    </div>
  </AppPage>
</template>

<style scoped>
.ob-preview {
  display: grid;
  gap: 12px;
  max-width: 560px;
}
.ob-preview__page {
  display: grid;
  gap: 12px;
  border-top: 4px solid var(--ob-accent, var(--ion-color-primary));
  padding-top: 12px;
}
.ob-preview__help {
  margin: 0;
  font-size: 0.85rem;
  opacity: 0.75;
}
.ob-preview__times {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.ob-preview small {
  display: block;
  font-size: 0.75rem;
  opacity: 0.7;
}
/* The personal link is one long word: it breaks anywhere instead of pushing the page off the phone's edge. */
.ob-preview code {
  overflow-wrap: anywhere;
}
</style>
