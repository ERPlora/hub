<script setup lang="ts">
// APPOINTMENT-F01, F04, F14, F22: the booking panel, the old agenda's side panel as a dialog.
// «New appointment»: the Customer (Customers' own search, which also creates a card with name and phone),
// the Services in order (only bookable ones), the Professional (only who does them all: the server's rule
// read through Services and Staff), the Day and the Time (with the «Free times»), the Min. (the services'
// sum unless typed) and the notes. The Min. and the Total are the professional's own for each service
// (Services · «Who does it»), the catalog's where she has none — what the server books. «Add appointment» books it. «Edit appointment» comes filled in, sends
// only what changed (`appointment.appointment.update`) and shows the history below; a series occurrence
// first asks «This appointment only» / «This and all following» (the latter edits the series from its
// date). An overlap asks first (409 `appointment.overlap_needs_confirmation`: «Book anyway» sends it again
// confirmed); any other refusal goes on top, a bad field under it, and what was typed stays.
import { Combo, type ComboOption, ConfirmDialog, FormModal, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonTextarea } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useLocale, useT } from '../composables/useT';
import { dayOf, timeOf, wallInput } from '../lib/clock';
import { formatMoney } from '../lib/format';
import { describeUpdate } from '../lib/outcome';
import { eligibleStaff, ownTerms, type ServiceFacts, type Terms } from '../lib/pickers';
import type { AppointmentOut, RecurringUpdateIn, UpdateIn } from '../operations';
import AppointmentHistory from './AppointmentHistory.vue';
import FreeSlots from './FreeSlots.vue';
import ServicesField from './ServicesField.vue';

/** What a tapped slot of the grid brings. */
export interface BookingPreset {
  day: string;
  time?: string;
  staffId?: string | null;
  staffName?: string;
}

const props = withDefaults(
  defineProps<{
    /** The appointment being edited; `null` = «New appointment». */
    appointment: AppointmentOut | null;
    /** The business's wall clock now (`YYYY-MM-DDTHH:MM`): a time before it is in the past. */
    businessNow: string;
    preset?: BookingPreset | null;
    /** The caller books for herself only: the professional is her own record. */
    ownStaff?: { id: string; name: string } | null;
  }>(),
  { preset: null, ownStaff: null },
);

const emit = defineEmits<{ saved: [appointment: AppointmentOut]; outcome: [text: string] }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const client = useLiveClient();

const facts = new Map<string, ServiceFacts>();
/** The chosen professional's own terms for the chosen services (empty: the catalog's, or as booked). */
const own = shallowRef(new Map<string, Terms>());
const termsOf = (id: string): Terms | undefined => own.value.get(id) ?? facts.get(id);

const customer = ref<CustomerSnapshot | null>(null);
const services = ref<ComboOption[]>([]);
const staff = ref<ComboOption | null>(null);
const day = ref('');
const time = ref('');
const minutes = ref('');
const minutesTouched = ref(false);
const notes = ref('');
const internalNotes = ref('');
const staffWarning = ref(false);

const create = useCommand('appointment.appointment.create');
const update = useCommand('appointment.appointment.update');
const editSeries = useCommand('appointment.recurring.update');
const pending = computed(() => create.pending.value || update.pending.value || editSeries.pending.value);
const failure = ref<ApiError | null>(null);
const overlap = ref<string | null>(null);
const scopeOpen = ref(false);

const editing = computed(() => props.appointment !== null);
const charged = computed(() => props.appointment?.sale_id != null);
const title = computed(() => (editing.value ? t('appointment.form.titleEdit') : t('appointment.form.titleNew')));
const serviceIds = computed(() => services.value.map((option) => option.id));
const total = computed(() => services.value.reduce((sum, option) => sum + (termsOf(option.id)?.price ?? 0), 0));
const typedMinutes = computed(() => (/^\d+$/.test(minutes.value.trim()) ? Number(minutes.value.trim()) : null));
const past = computed(() => !!day.value && !!time.value && wallInput(day.value, time.value) < props.businessNow);
const ready = computed(
  () => (editing.value || !!customer.value) && services.value.length > 0 && !!staff.value && !!day.value && !!time.value,
);
const searchStaff = (query: string) => eligibleStaff(client, serviceIds.value, query);

function sumMinutes(): string {
  const sum = services.value.reduce((acc, option) => acc + (termsOf(option.id)?.minutes ?? 0), 0);
  return sum ? String(sum) : '';
}

function reset(): void {
  const booked = props.appointment;
  failure.value = null;
  overlap.value = null;
  scopeOpen.value = false;
  staffWarning.value = false;
  minutesTouched.value = false;
  own.value = new Map();
  if (booked) {
    for (const line of booked.services) facts.set(line.service_id, { name: line.name, minutes: line.duration_minutes, price: line.price });
    customer.value = null;
    services.value = booked.services.map((line) => ({ id: line.service_id, label: line.name }));
    staff.value = booked.staff_id ? { id: booked.staff_id, label: booked.staff_name } : null;
    day.value = dayOf(booked.start);
    time.value = timeOf(booked.start);
    minutes.value = String(booked.duration_minutes);
    notes.value = booked.notes;
    internalNotes.value = booked.internal_notes;
    return;
  }
  const preset = props.preset;
  customer.value = null;
  services.value = [];
  staff.value = props.ownStaff
    ? { id: props.ownStaff.id, label: props.ownStaff.name }
    : preset?.staffId
      ? { id: preset.staffId, label: preset.staffName ?? '' }
      : null;
  day.value = preset?.day ?? props.businessNow.slice(0, 10);
  time.value = preset?.time ?? '';
  minutes.value = '';
  notes.value = '';
  internalNotes.value = '';
}

/** The professional and services the panel opened with: as booked, nothing to ask Services. */
const termsKey = (): string => `${staff.value?.id ?? ''}|${serviceIds.value.join()}`;
let baseline = '';
/** Number of the last question for her terms: an older answer is dropped. */
let asked = 0;

watch(
  () => [open.value, props.appointment?.id] as const,
  ([isOpen]) => {
    if (isOpen) reset();
    asked += 1;
    baseline = termsKey();
  },
  { immediate: true },
);

// The professional or the services changed by hand: her own minutes and prices (as booked until then).
watch(termsKey, async (key) => {
  const mine = ++asked;
  const memberId = staff.value?.id;
  if (key === baseline || !memberId || !serviceIds.value.length) {
    own.value = new Map();
    return;
  }
  try {
    const terms = await ownTerms(client, memberId, serviceIds.value);
    if (mine !== asked) return;
    own.value = terms;
    if (!minutesTouched.value) minutes.value = sumMinutes();
  } catch {
    // The catalog's stay; the server books her own anyway.
  }
});

// New services: their sum unless the minutes were typed; a professional who does not do them all goes.
watch(serviceIds, async (ids, before) => {
  if (ids.join() === (before ?? []).join()) return;
  if (!minutesTouched.value) minutes.value = sumMinutes();
  const chosen = staff.value;
  if (!chosen || props.ownStaff || !ids.length) return;
  try {
    const allowed = await eligibleStaff(client, ids, '');
    if (staff.value?.id === chosen.id && !allowed.some((option) => option.id === chosen.id)) {
      staff.value = null;
      staffWarning.value = true;
    }
  } catch {
    // The server judges it when saving.
  }
});

function pickStaff(option: ComboOption | null): void {
  staff.value = option;
  staffWarning.value = false;
}

function typeMinutes(value: string): void {
  minutes.value = value;
  minutesTouched.value = true;
}

const fieldOf: Record<string, string> = { duration_minutes: 'minutes', staff_id: 'staff', customer_id: 'customer' };
const shown = computed<ApiError | null>(() => {
  const error = failure.value;
  if (!error?.fields) return error;
  const fields = Object.fromEntries(Object.entries(error.fields).map(([key, message]) => [fieldOf[key] ?? key.split('.')[0], message]));
  return { ...error, fields } as ApiError;
});

async function attempt(run: () => Promise<AppointmentOut>): Promise<void> {
  failure.value = null;
  try {
    const saved = await run();
    emit('saved', saved);
    open.value = false;
  } catch (error) {
    const caught = error as ApiError;
    if (caught?.code === 'appointment.overlap_needs_confirmation') overlap.value = caught.message;
    else failure.value = caught;
  }
}

function bookNew(confirmOverlap: boolean): Promise<AppointmentOut> {
  return create.run({
    customer_id: customer.value?.customer_id ?? null,
    services: serviceIds.value.map((id) => ({ service_id: id })),
    staff_id: staff.value?.id ?? null,
    start: wallInput(day.value, time.value),
    ...(minutesTouched.value && typedMinutes.value ? { duration_minutes: typedMinutes.value } : {}),
    notes: notes.value,
    internal_notes: internalNotes.value,
    confirm_overlap: confirmOverlap,
  });
}

/** What the edit changes of the appointment's slot (time, length, professional, services). */
function slotChanges(booked: AppointmentOut): Partial<UpdateIn> {
  const out: Partial<UpdateIn> = {};
  if (wallInput(day.value, time.value) !== booked.start.slice(0, 16)) out.start = wallInput(day.value, time.value);
  if (minutesTouched.value && typedMinutes.value && typedMinutes.value !== booked.duration_minutes) {
    out.duration_minutes = typedMinutes.value;
  }
  if (staff.value && staff.value.id !== booked.staff_id) out.staff_id = staff.value.id;
  if (serviceIds.value.join() !== booked.services.map((line) => line.service_id).join()) {
    out.services = serviceIds.value.map((id) => ({ service_id: id }));
  }
  return out;
}

function noteChanges(booked: AppointmentOut): Partial<UpdateIn> {
  const out: Partial<UpdateIn> = {};
  if (notes.value !== booked.notes) out.notes = notes.value;
  if (internalNotes.value !== booked.internal_notes) out.internal_notes = internalNotes.value;
  return out;
}

function saveThis(booked: AppointmentOut, confirmOverlap: boolean): Promise<AppointmentOut> {
  return update.run({ id: booked.id, ...slotChanges(booked), ...noteChanges(booked), confirm_overlap: confirmOverlap });
}

async function saveFollowing(): Promise<void> {
  const booked = props.appointment;
  if (!booked?.recurring_id || !booked.occurrence_date) return;
  const slot = slotChanges(booked);
  const change: RecurringUpdateIn = { id: booked.recurring_id, from_date: booked.occurrence_date };
  if (slot.start) {
    change.time = time.value.length === 4 ? `0${time.value}` : time.value;
    if (day.value !== dayOf(booked.start)) change.day_of_week = (new Date(`${day.value}T00:00:00Z`).getUTCDay() + 6) % 7;
  }
  if (slot.duration_minutes) change.duration_minutes = slot.duration_minutes;
  if (slot.staff_id) change.staff_id = slot.staff_id;
  if (slot.services) change.services = slot.services;
  scopeOpen.value = false;
  failure.value = null;
  try {
    const result = await editSeries.run(change);
    const notesOnly = noteChanges(booked);
    if (Object.keys(notesOnly).length) await update.run({ id: booked.id, ...notesOnly });
    const said = describeUpdate(result, change, t, locale.value);
    emit('outcome', [said.summary, said.skipped.join('; ')].filter(Boolean).join(' '));
    open.value = false;
  } catch (error) {
    failure.value = error as ApiError;
  }
}

async function save(confirmOverlap = false): Promise<void> {
  const booked = props.appointment;
  if (!booked) {
    await attempt(() => bookNew(confirmOverlap));
    return;
  }
  if (booked.recurring_id && Object.keys(slotChanges(booked)).length && !confirmOverlap) {
    scopeOpen.value = true;
    return;
  }
  await attempt(() => saveThis(booked, confirmOverlap));
}

async function bookAnyway(): Promise<void> {
  overlap.value = null;
  await save(true);
}

function thisOnly(): void {
  scopeOpen.value = false;
  const booked = props.appointment;
  if (booked) void attempt(() => saveThis(booked, false));
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="appointment-form"
    :title="title"
    :submit-label="editing ? $t('appointment.form.save') : $t('appointment.form.create')"
    :pending="pending"
    :error="shown"
    :submit-disabled="!ready || charged"
    @submit="save()"
  >
    <template #default="{ fieldErrors }">
      <div class="appointment-form">
        <p
          v-if="editing"
          class="appointment-form__hint"
        >
          <strong>{{ appointment?.number }}</strong> · {{ appointment?.customer_name || $t('appointment.list.erasedCustomer') }} ·
          {{ $t('appointment.form.hint') }}
        </p>
        <InlineFeedback
          v-if="charged"
          tone="info"
          data-testid="appointment-form-charged"
        >
          {{ $t('appointment.form.charged') }}
        </InlineFeedback>
        <div
          v-if="!editing"
          class="appointment-form__customer"
          data-testid="appointment-form-customer"
        >
          <span class="appointment-form__label">{{ $t('appointment.form.customer') }}</span>
          <CustomerSearch v-model="customer" />
          <small
            v-if="fieldErrors.customer"
            class="appointment-form__error"
          >{{ fieldErrors.customer }}</small>
        </div>
        <div class="appointment-form__services">
          <ServicesField
            v-model="services"
            :facts="facts"
            testid="appointment-form"
            :error-text="fieldErrors.services"
            :disabled="charged"
          />
          <small
            v-if="services.length"
            class="appointment-form__total"
            data-testid="appointment-form-total"
          >{{ $t('appointment.form.total') }}: {{ formatMoney(total, locale) }}</small>
        </div>
        <Combo
          testid="appointment-form-staff"
          :model-value="staff"
          :search="searchStaff"
          :label="t('appointment.form.staff')"
          :placeholder="t('appointment.form.pickStaff')"
          :empty-label="t('appointment.form.staffNone')"
          :error-text="fieldErrors.staff"
          :clearable="!ownStaff"
          :disabled="!!ownStaff || charged"
          @update:model-value="pickStaff"
        />
        <small
          v-if="ownStaff"
          class="appointment-form__note"
          data-testid="appointment-form-own"
        >{{ $t('appointment.form.ownOnly') }}</small>
        <InlineFeedback
          v-if="staffWarning"
          tone="warning"
          data-testid="appointment-form-staff-warning"
        >
          {{ $t('appointment.form.staffNotForService') }}
        </InlineFeedback>
        <div class="appointment-form__when">
          <ion-input
            data-testid="appointment-form-day"
            type="date"
            :value="day"
            :label="$t('appointment.form.day')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="charged"
            @ion-input="day = text($event.detail.value)"
          />
          <ion-input
            data-testid="appointment-form-time"
            type="time"
            :value="time"
            :label="$t('appointment.form.time')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="charged"
            :error-text="fieldErrors.start"
            :class="invalid(fieldErrors.start)"
            @ion-input="time = text($event.detail.value)"
          />
          <ion-input
            data-testid="appointment-form-minutes"
            type="number"
            inputmode="numeric"
            min="1"
            :value="minutes"
            :label="$t('appointment.form.minutes')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :disabled="charged"
            :error-text="fieldErrors.minutes"
            :class="invalid(fieldErrors.minutes)"
            @ion-input="typeMinutes(text($event.detail.value))"
          />
        </div>
        <InlineFeedback
          v-if="past"
          tone="warning"
          data-testid="appointment-form-past"
        >
          {{ $t('appointment.form.pastNotice') }}
        </InlineFeedback>
        <FreeSlots
          v-if="services.length && staff && day && !charged"
          :date="day"
          :service-ids="serviceIds"
          :staff-id="staff.id"
          :selected="time"
          :duration-minutes="minutesTouched ? typedMinutes : null"
          :exclude-id="appointment?.id ?? null"
          @pick="time = $event"
        />
        <ion-textarea
          data-testid="appointment-form-notes"
          :value="notes"
          :label="$t('appointment.form.notes')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :maxlength="2000"
          :error-text="fieldErrors.notes"
          @ion-input="notes = text($event.detail.value)"
        />
        <ion-textarea
          data-testid="appointment-form-internal_notes"
          :value="internalNotes"
          :label="$t('appointment.form.internalNotes')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :auto-grow="true"
          :maxlength="2000"
          :error-text="fieldErrors.internal_notes"
          @ion-input="internalNotes = text($event.detail.value)"
        />
        <section
          v-if="appointment"
          class="appointment-form__history"
        >
          <h3>{{ $t('appointment.form.history') }}</h3>
          <AppointmentHistory :appointment-id="appointment.id" />
        </section>
      </div>
    </template>
  </FormModal>
  <ConfirmDialog
    :open="overlap !== null"
    testid="appointment-overlap"
    tone="warning"
    :title="t('appointment.overlap.title')"
    :message="overlap ?? ''"
    :confirm-label="t('appointment.overlap.confirm')"
    :cancel-label="t('appointment.overlap.cancel')"
    :pending="pending"
    @update:open="(value: boolean) => !value && (overlap = null)"
    @confirm="bookAnyway"
    @cancel="overlap = null"
  />
  <FormModal
    v-model:open="scopeOpen"
    testid="appointment-scope"
    size="sm"
    :title="t('appointment.scope.title')"
    :pending="pending"
    @submit="thisOnly"
  >
    <p>{{ $t('appointment.scope.message') }}</p>
    <template #footer>
      <ion-button
        fill="outline"
        data-testid="appointment-scope-this"
        @click="thisOnly"
      >
        {{ $t('appointment.scope.thisOnly') }}
      </ion-button>
      <ion-button
        data-testid="appointment-scope-following"
        @click="saveFollowing"
      >
        {{ $t('appointment.scope.following') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.appointment-form {
  display: grid;
  gap: 14px;
}
.appointment-form__when {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr) minmax(0, 0.7fr);
  gap: 10px;
}
.appointment-form__label {
  display: block;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
  margin-bottom: 4px;
}
.appointment-form__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 6px;
}
.appointment-form__hint,
.appointment-form__note,
.appointment-form__total {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
}
.appointment-form__error {
  color: var(--ion-color-danger, #c5000f);
}
.appointment-form__history h3 {
  font-size: 0.95rem;
  margin: 8px 0;
}
@media (max-width: 520px) {
  .appointment-form__when {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
