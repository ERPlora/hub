<script setup lang="ts">
// RESERVATION-F06, F08, F23: the booking panel. «New reservation» asks for the Customer (Customers' own
// search, which also creates a card; picking one fills the guest's name, phone and email) or the guest's
// Name and Phone (the server finds the card with that phone or makes one), the Date, the Time, the Party,
// the Duration (empty: the book's default), the Table — the free ones at that time, the ones that fit the
// party first (`reservation.availability.tables`) —, where it was booked and the notes. A full slot asks
// first («Book anyway», `overbook`, never for online bookings); a refusal goes on top, a bad field under
// it, and what was typed stays. «Edit reservation» sends only what changed (`no_table` to leave it without
// one); once seated, completed, cancelled or not shown, only its notes change, as the server says.
import { Combo, type ComboOption, ConfirmDialog, FormModal, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonLabel, IonSegment, IonSegmentButton, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useT } from '../composables/useT';
import { hhmm } from '../lib/clock';
import type { BookingSource, FreeTableOut, ReservationIn, ReservationOut, ReservationPatchIn } from '../operations';

const props = defineProps<{
  /** The reservation being edited; `null` = «New reservation». */
  reservation: ReservationOut | null;
  /** The day a new reservation starts on (the day the book is on). */
  day: string;
}>();
const emit = defineEmits<{ saved: [reservation: ReservationOut] }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const client = useLiveClient();
const create = useCommand('reservation.reservation.create');
const update = useCommand('reservation.reservation.update');
const pending = computed(() => create.pending.value || update.pending.value);

const SOURCES: readonly BookingSource[] = ['phone', 'in_person'];
/** What the server keeps once a reservation is seated, completed, cancelled or not shown. */
const OPEN_STATUSES = ['pending', 'confirmed'];

const customer = ref<CustomerSnapshot | null>(null);
const name = ref('');
const phone = ref('');
const email = ref('');
const date = ref('');
const time = ref('');
const party = ref('2');
const duration = ref('');
const table = ref<ComboOption | null>(null);
const source = ref<BookingSource>('phone');
const notes = ref('');
const internalNotes = ref('');
const failure = ref<ApiError | null>(null);
const overbookMessage = ref<string | null>(null);
/** The seats of the tables offered, by id: to warn when the one chosen is small for the party. */
const seats = new Map<string, number>();

const editing = computed(() => props.reservation !== null);
const notesOnly = computed(() => !!props.reservation && !OPEN_STATUSES.includes(props.reservation.status));
const partySize = computed(() => (/^\d+$/.test(party.value.trim()) ? Number(party.value.trim()) : null));
const minutes = computed(() => (/^\d+$/.test(duration.value.trim()) ? Number(duration.value.trim()) : null));
const ready = computed(() => (!!customer.value || !!name.value.trim()) && !!date.value && !!time.value && !!partySize.value);
const title = computed(() => (editing.value ? t('reservation.form.titleEdit') : t('reservation.form.titleNew')));
const small = computed(() => {
  const chosen = table.value;
  const capacity = chosen ? seats.get(chosen.id) : undefined;
  if (!chosen || capacity === undefined || !partySize.value || partySize.value <= capacity) return '';
  return t('reservation.form.smallTable', { table: chosen.label, capacity, party: partySize.value });
});

function reset(): void {
  failure.value = null;
  overbookMessage.value = null;
  seats.clear();
  const booked = props.reservation;
  customer.value = null;
  name.value = booked?.guest_name ?? '';
  phone.value = booked?.guest_phone ?? '';
  email.value = booked?.guest_email ?? '';
  date.value = booked?.date ?? props.day;
  time.value = booked ? hhmm(booked.time) : '';
  party.value = String(booked?.party_size ?? 2);
  duration.value = booked ? String(booked.duration_minutes) : '';
  table.value = booked?.table_id ? { id: booked.table_id, label: booked.table_label } : null;
  if (booked?.table_id && booked.table_capacity !== null) seats.set(booked.table_id, booked.table_capacity);
  source.value = 'phone';
  notes.value = booked?.notes ?? '';
  internalNotes.value = booked?.internal_notes ?? '';
}

watch(
  () => [open.value, props.reservation?.id] as const,
  ([isOpen]) => {
    if (isOpen) reset();
  },
  { immediate: true },
);

// A card picked from Customers fills the guest's name, phone and email (read whole: the pick brings only
// its tax details).
watch(customer, async (picked) => {
  if (!picked) return;
  name.value = picked.customer_name;
  try {
    const card = await client.api.call('customer.customer.detail', { id: picked.customer_id });
    if (customer.value?.customer_id !== picked.customer_id) return;
    phone.value = card.phone ?? '';
    email.value = card.email ?? '';
  } catch {
    // The server copies them from the card anyway.
  }
});

async function searchTables(query: string): Promise<ComboOption[]> {
  if (!date.value || !time.value) return [];
  const answer = await client.api.call('reservation.availability.tables', {
    date: date.value,
    time: hhmm(time.value),
    ...(partySize.value ? { party_size: partySize.value } : {}),
    ...(minutes.value ? { duration_minutes: minutes.value } : {}),
    ...(props.reservation ? { exclude_id: props.reservation.id } : {}),
    ...(query.trim() ? { search: query.trim() } : {}),
  });
  const free = answer.rows.filter((row: FreeTableOut) => row.free);
  for (const row of free) seats.set(row.id, row.capacity);
  return free.map((row: FreeTableOut) => ({
    id: row.id,
    label: row.label,
    hint: t(row.fits ? 'reservation.form.tableHint' : 'reservation.form.tableSmall', {
      capacity: row.capacity,
      zone: row.zone_name || t('reservation.form.noZone'),
    }),
  }));
}

function newBooking(overbook: boolean): ReservationIn {
  return {
    ...(customer.value ? { customer_id: customer.value.customer_id } : {}),
    guest_name: name.value.trim(),
    guest_phone: phone.value.trim(),
    guest_email: email.value.trim(),
    date: date.value,
    time: hhmm(time.value),
    party_size: partySize.value ?? 0,
    ...(minutes.value ? { duration_minutes: minutes.value } : {}),
    ...(table.value ? { table_id: table.value.id } : {}),
    source: source.value,
    notes: notes.value,
    internal_notes: internalNotes.value,
    overbook,
  };
}

/** What the edit changes (only what differs from the reservation as it was opened). */
function changes(booked: ReservationOut, overbook: boolean): ReservationPatchIn {
  const out: ReservationPatchIn = { id: booked.id, overbook };
  if (notes.value !== booked.notes) out.notes = notes.value;
  if (internalNotes.value !== booked.internal_notes) out.internal_notes = internalNotes.value;
  if (notesOnly.value) return out;
  if (name.value.trim() !== booked.guest_name) out.guest_name = name.value.trim();
  if (phone.value.trim() !== booked.guest_phone) out.guest_phone = phone.value.trim();
  if (email.value.trim() !== booked.guest_email) out.guest_email = email.value.trim();
  if (date.value !== booked.date) out.date = date.value;
  if (hhmm(time.value) !== hhmm(booked.time)) out.time = hhmm(time.value);
  if (partySize.value && partySize.value !== booked.party_size) out.party_size = partySize.value;
  if (minutes.value && minutes.value !== booked.duration_minutes) out.duration_minutes = minutes.value;
  if ((table.value?.id ?? null) !== booked.table_id) {
    if (table.value) out.table_id = table.value.id;
    else out.no_table = true;
  }
  return out;
}

async function save(overbook = false): Promise<void> {
  failure.value = null;
  const booked = props.reservation;
  try {
    const saved = booked ? await update.run(changes(booked, overbook)) : await create.run(newBooking(overbook));
    emit('saved', saved);
    open.value = false;
  } catch (error) {
    const caught = error as ApiError;
    // The server says when a full slot may be booked anyway (`fields.overbook`): the staff, never online.
    if (caught?.code === 'reservation.no_capacity' && caught.fields?.overbook && !overbook) overbookMessage.value = caught.message;
    else failure.value = caught;
  }
}

async function bookAnyway(): Promise<void> {
  overbookMessage.value = null;
  await save(true);
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="reservation-form"
    :title="title"
    :submit-label="editing ? $t('reservation.form.submitEdit') : $t('reservation.form.submitNew')"
    :pending="pending"
    :error="failure"
    :submit-disabled="!ready"
    @submit="save()"
  >
    <template #default="{ fieldErrors }">
      <div class="reservation-form">
        <InlineFeedback
          v-if="notesOnly && reservation"
          tone="info"
          data-testid="reservation-form-notes-only"
        >
          {{ $t('reservation.form.notesOnly', { status: t(`reservation.status.${reservation.status}`).toLowerCase() }) }}
        </InlineFeedback>
        <div
          v-if="!editing"
          class="reservation-form__customer"
          data-testid="reservation-form-customer"
        >
          <span class="reservation-form__label">{{ $t('reservation.form.customer') }}</span>
          <CustomerSearch v-model="customer" />
        </div>
        <div class="reservation-form__pair">
          <ion-input
            data-testid="reservation-form-guest_name"
            :value="name"
            :label="$t('reservation.form.name')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="200"
            :disabled="notesOnly"
            :error-text="fieldErrors.guest_name"
            :class="invalid(fieldErrors.guest_name)"
            @ion-input="name = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-form-guest_phone"
            type="tel"
            :value="phone"
            :label="$t('reservation.form.phone')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="60"
            :disabled="notesOnly"
            :error-text="fieldErrors.guest_phone"
            :class="invalid(fieldErrors.guest_phone)"
            @ion-input="phone = text($event.detail.value)"
          />
        </div>
        <ion-input
          data-testid="reservation-form-guest_email"
          type="email"
          :value="email"
          :label="$t('reservation.form.email')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="254"
          :disabled="notesOnly"
          :error-text="fieldErrors.guest_email"
          :class="invalid(fieldErrors.guest_email)"
          @ion-input="email = text($event.detail.value)"
        />
        <div class="reservation-form__when">
          <ion-input
            data-testid="reservation-form-date"
            type="date"
            :value="date"
            :label="$t('reservation.form.date')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="notesOnly"
            :error-text="fieldErrors.date"
            :class="invalid(fieldErrors.date)"
            @ion-input="date = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-form-time"
            type="time"
            :value="time"
            :label="$t('reservation.form.time')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="notesOnly"
            :error-text="fieldErrors.time"
            :class="invalid(fieldErrors.time)"
            @ion-input="time = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-form-party_size"
            type="number"
            inputmode="numeric"
            min="1"
            :value="party"
            :label="$t('reservation.form.party')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="notesOnly"
            :error-text="fieldErrors.party_size"
            :class="invalid(fieldErrors.party_size)"
            @ion-input="party = text($event.detail.value)"
          />
          <ion-input
            data-testid="reservation-form-duration_minutes"
            type="number"
            inputmode="numeric"
            min="1"
            :value="duration"
            :label="$t('reservation.form.duration')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="notesOnly"
            :error-text="fieldErrors.duration_minutes"
            :class="invalid(fieldErrors.duration_minutes)"
            @ion-input="duration = text($event.detail.value)"
          />
        </div>
        <Combo
          v-model="table"
          testid="reservation-form-table"
          :search="searchTables"
          :label="t('reservation.form.table')"
          :placeholder="t('reservation.form.pickTable')"
          :empty-label="date && time ? t('reservation.form.tablesNone') : t('reservation.form.pickFirst')"
          :error-text="fieldErrors.table_id"
          :disabled="notesOnly"
          clearable
        />
        <InlineFeedback
          v-if="small"
          tone="warning"
          data-testid="reservation-form-small"
        >
          {{ small }}
        </InlineFeedback>
        <div
          v-if="!editing"
          class="reservation-form__source"
        >
          <span class="reservation-form__label">{{ $t('reservation.form.source') }}</span>
          <ion-segment
            data-testid="reservation-form-source"
            :value="source"
            mode="md"
            @ion-change="source = ($event.detail.value as BookingSource) ?? 'phone'"
          >
            <ion-segment-button
              v-for="option in SOURCES"
              :key="option"
              :value="option"
              :data-testid="`reservation-form-source-${option}`"
            >
              <ion-label>{{ $t(`reservation.source.${option}`) }}</ion-label>
            </ion-segment-button>
          </ion-segment>
        </div>
        <ion-textarea
          data-testid="reservation-form-notes"
          :value="notes"
          :label="$t('reservation.form.notes')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :maxlength="2000"
          :error-text="fieldErrors.notes"
          @ion-input="notes = text($event.detail.value)"
        />
        <ion-textarea
          data-testid="reservation-form-internal_notes"
          :value="internalNotes"
          :label="$t('reservation.form.internalNotes')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :maxlength="2000"
          :error-text="fieldErrors.internal_notes"
          @ion-input="internalNotes = text($event.detail.value)"
        />
      </div>
    </template>
  </FormModal>
  <ConfirmDialog
    :open="overbookMessage !== null"
    testid="reservation-overbook"
    tone="warning"
    :title="t('reservation.overbook.title')"
    :message="t('reservation.overbook.message', { message: overbookMessage ?? '' })"
    :confirm-label="t('reservation.overbook.confirm')"
    :cancel-label="t('reservation.cancelButton')"
    :pending="pending"
    @update:open="(value: boolean) => !value && (overbookMessage = null)"
    @confirm="bookAnyway"
    @cancel="overbookMessage = null"
  />
</template>

<style scoped>
.reservation-form {
  display: grid;
  gap: 14px;
}
.reservation-form__pair,
.reservation-form__when {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
}
.reservation-form__customer,
.reservation-form__source {
  display: grid;
  gap: 6px;
}
.reservation-form__label {
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
