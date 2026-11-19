<script setup lang="ts">
// The customer's booking flow: services, a professional or «No preference», a day and a free time, name and mobile,
// book; then the booking seen and cancelled with the personal link. One-shot calls (what is public is not followed
// live), and a price in the business's money (BASE-F50: «20,00 zł» in Poland, a dash until it is known), as the diary
// paints it. It is the public booking page itself when that page gives it base's public door (`PUBLIC_DOOR`: the
// calls, the money and the customer's words); without it, the team's preview on the dev server (routes.ts; WORKBOOK
// «Vista previa de la reserva»), through the session.
import { EmptyState, InlineFeedback, useRefusal } from '@erplora/ui/components';
import { ApiError, useLiveClient } from '@erplora/ui/sdk';
import { AppPage } from '@erplora/ui/shell';
import { IonButton, IonCheckbox, IonInput, IonSelect, IonSelectOption, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, inject, onMounted, ref, watch } from 'vue';

import { dayOf, formatTime, timeOf } from '../../../appointment/frontend/lib/clock';
import { formatMoney, useBusinessMoney } from '../../../appointment/frontend/lib/format';
import BookingResult from '../components/BookingResult.vue';
import PublicBookingHeader from '../components/PublicBookingHeader.vue';
import PublicBookingSubmit from '../components/PublicBookingSubmit.vue';
import { useLocale, useT } from '../composables/useT';
import { PUBLIC_DOOR } from '../lib/door';
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
const MIN_SUBMIT_MS = 3000;

const door = inject(PUBLIC_DOOR, null);
const openedAt = Date.now();
const api = door?.api ?? useLiveClient().api;
const t = useT();
const locale = useLocale();
const money = door?.money ?? useBusinessMoney();
// The customer's words on the public page; the team's on its preview.
const heading = computed(() => (door ? t('online_booking.door.title') : t('online_booking.preview.title')));
const intro = computed(() => (door ? t('online_booking.door.intro') : t('online_booking.preview.intro')));
const noServices = computed(() => (door ? t('online_booking.door.noServices') : t('online_booking.preview.noServices')));

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
    info.value = await api.call('online_booking.public.page', {});
    services.value = (await api.call('online_booking.public.services', { limit: SERVICE_WINDOW })).rows;
    servicesLoaded.value = true;
  } catch (failure) {
    loadError.value = asError(failure);
  }
});

function priceAndLength(service: PublicServiceOut): string {
  const parts = [
    service.price === null ? '' : formatMoney(service.price, locale.value, money.value),
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
const website = ref('');

function pick(id: string, on: boolean): void {
  chosen.value = on ? [...chosen.value.filter((item) => item !== id), id] : chosen.value.filter((item) => item !== id);
  changed('service_ids');
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
    const answer = await api.call('online_booking.public.slots', {
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
// What is picked or typed is told by the name the server refuses it with (`start` for the day and the time).
const { fieldErrors, showsError, changed } = useRefusal(bookError);
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const ready = computed(() => !!start.value && !!name.value.trim() && !!phone.value.trim() && !booking.value);

async function minimumWait(): Promise<void> {
  const remaining = openedAt + MIN_SUBMIT_MS - Date.now();
  if (remaining > 0) await new Promise((resolve) => setTimeout(resolve, remaining));
}

async function book(): Promise<void> {
  if (!ready.value) return;
  booking.value = true;
  bookError.value = null;
  try {
    if (door) await minimumWait();
    booked.value = await api.call('online_booking.public.book', {
      service_ids: chosen.value,
      ...(staff.value ? { staff_id: staff.value } : {}),
      start: start.value,
      name: name.value.trim(),
      phone: phone.value.trim(),
      email: email.value.trim(),
      notes: notes.value.trim(),
      ...(door ? { website: website.value } : {}),
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
    seen.value = await api.call(op, { token: booked.value.token });
  } catch (failure) {
    linkError.value = asError(failure);
  } finally {
    linkPending.value = false;
  }
}

function again(): void {
  booked.value = null;
  seen.value = null;
  start.value = '';
  name.value = phone.value = email.value = notes.value = '';
  website.value = '';
  chosen.value = [];
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <AppPage
    :title="heading"
    content-layout="detail"
  >
    <div
      class="ob-preview"
      data-testid="ob-preview"
    >
      <h2>{{ heading }}</h2>
      <p
        v-if="!door || !servicesLoaded || services.length > 0"
        class="ob-preview__help"
        data-testid="ob-preview-intro"
      >
        {{ intro }}
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
        data-testid="ob-preview-page"
        :style="{ '--ob-accent': info.primary_color }"
      >
        <PublicBookingHeader
          v-if="door"
          :info="info"
        />
        <template v-else>
          <h3 data-testid="ob-preview-title">
            {{ info.title }}
          </h3>
          <p v-if="info.welcome_message">
            {{ info.welcome_message }}
          </p>
        </template>

        <template v-if="!booked">
          <h4 v-if="!door || services.length">
            {{ $t('online_booking.preview.services') }}
          </h4>
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
          <EmptyState
            v-if="servicesLoaded && !services.length"
            data-testid="ob-preview-no-services"
            icon="ion:calendar-outline"
            :message="noServices"
          />

          <template v-if="!door || services.length">
            <ion-select
              v-if="info.allow_staff_selection"
              data-testid="ob-preview-staff"
              :value="staff"
              :label="$t('online_booking.preview.professional')"
              label-placement="floating"
              fill="outline"
              mode="md"
              interface="popover"
              @ion-change="staff = text($event.detail.value); changed('staff_id')"
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
              @ion-change="day = text($event.detail.value); changed('start')"
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
                  @click="start = wallOf(slot.start); changed('start')"
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
              @ion-input="name = text($event.detail.value); changed('name')"
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
              @ion-input="phone = text($event.detail.value); changed('phone')"
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
              @ion-input="email = text($event.detail.value); changed('email')"
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
              @ion-input="notes = text($event.detail.value); changed('notes')"
            />
            <InlineFeedback
              v-if="showsError"
              tone="danger"
              data-testid="ob-preview-form-error"
            >
              {{ bookError?.message }}
            </InlineFeedback>
            <PublicBookingSubmit
              v-if="door"
              v-model:website="website"
              :business-name="info.business_name"
              :privacy-policy-url="info.privacy_policy_url"
              :ready="ready"
              :pending="booking"
              @submit="book"
            />
            <ion-button
              v-else
              data-testid="ob-preview-book"
              :disabled="!ready"
              @click="book"
            >
              {{ $t('online_booking.preview.book') }}
            </ion-button>
          </template>
        </template>

        <BookingResult
          v-else
          :booked="booked"
          :seen="seen"
          :pending="linkPending"
          :error="linkError?.message ?? ''"
          @action="byLink"
          @again="again"
        />
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
</style>
