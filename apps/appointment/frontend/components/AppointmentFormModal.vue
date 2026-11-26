<script setup lang="ts">
// «Duration (min)» and the Total are the professional's own for each service, the catalog's where she has none: what
// the server books. An overlap (409 `appointment.overlap_needs_confirmation`) asks before «Book anyway» sends it again.
import { type ComboOption, ConfirmDialog, DateField, FormModal, InlineFeedback, StatusPill, TimeField } from '@erplora/ui/components';
import { type ApiError, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import FieldGroup from '../../../../base/frontend/components/FieldGroup.vue';
import { useGroupChange } from '../../../../base/frontend/lib/group-change';
import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useLocale, useT } from '../composables/useT';
import { type Chosen, newBooking, noteChanges, refusedFields, seriesChange, slotChanges } from '../lib/booking';
import { dayOf, timeOf, wallInput } from '../lib/clock';
import { formatMoney, useBusinessMoney } from '../lib/format';
import { describeUpdate } from '../lib/outcome';
import { eligibleStaff, ownTerms, type ServiceFacts, type Terms } from '../lib/pickers';
import { STATUS_TONE } from '../lib/states';
import type { AppointmentOut } from '../operations';
import AppointmentHistory from './AppointmentHistory.vue';
import BookingNotes from './BookingNotes.vue';
import BookingSummary from './BookingSummary.vue';
import DurationPicker from './DurationPicker.vue';
import FoldedSection from './FoldedSection.vue';
import FreeSlots from './FreeSlots.vue';
import ServicesField from './ServicesField.vue';
import StaffField from './StaffField.vue';

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

const canDismiss = useUnsavedFormOnOpen('appointment-form', () => ({ customer: customer.value, services: services.value, staff: staff.value, day: day.value, time: time.value, minutes: minutesTouched.value ? minutes.value : openedMinutes.value, notes: notes.value, internalNotes: internalNotes.value }), open);

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const money = useBusinessMoney();

const facts = new Map<string, ServiceFacts>();
/** The chosen professional's own terms for the chosen services (empty: the catalog's, or as booked). */
const own = shallowRef(new Map<string, Terms>());
const termsOf = (id: string): Terms | undefined => own.value.get(id) ?? facts.get(id);

const customer = ref<CustomerSnapshot | null>(null);
/** The customer is chosen in a window of her search, where no field of the form is typed in: choosing another one
 *  takes the customer's refusal away. */
const customerChanged = useGroupChange('customerGroup');
function chooseCustomer(chosen: CustomerSnapshot | null): void {
  customer.value = chosen;
  customerChanged();
}
const services = ref<ComboOption[]>([]);
const staff = ref<ComboOption | null>(null);
const day = ref('');
const time = ref('');
const minutes = ref('');
const minutesTouched = ref(false);
const openedMinutes = ref('');
const notes = ref('');
const internalNotes = ref('');
const staffWarning = ref(false);
/** The free times say the professional does not work that day: no other time of it can be booked. */
const slotsOff = ref(false);

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
const asking = computed(() => services.value.length > 0 && !!staff.value && !!day.value && !charged.value);
const chosen = computed<Chosen>(() => ({
  day: day.value,
  time: time.value,
  minutes: minutesTouched.value ? typedMinutes.value : null,
  staffId: staff.value?.id ?? null,
  serviceIds: serviceIds.value,
  notes: notes.value,
  internalNotes: internalNotes.value,
}));

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
    openedMinutes.value = minutes.value;
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
  openedMinutes.value = '';
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

// New services: their sum unless the minutes were typed (the services as booked: the length as booked); a
// professional who does not do them all goes.
watch(serviceIds, async (ids, before) => {
  if (ids.join() === (before ?? []).join()) return;
  const asBooked = ids.join() === (props.appointment?.services.map((line) => line.service_id).join() ?? null);
  if (!minutesTouched.value) minutes.value = asBooked ? openedMinutes.value : sumMinutes();
  const picked = staff.value;
  if (!picked || props.ownStaff || !ids.length) return;
  try {
    const allowed = await eligibleStaff(client, ids, '');
    if (staff.value?.id === picked.id && !allowed.some((option) => option.id === picked.id)) {
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

/** Back to the services' sum: a new appointment follows them again; an edit sends the sum. */
function useSum(): void {
  minutes.value = sumMinutes();
  minutesTouched.value = editing.value;
}

const shown = computed(() => refusedFields(failure.value));

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
  return create.run(newBooking(chosen.value, customer.value?.customer_id ?? null, confirmOverlap));
}

function saveThis(booked: AppointmentOut, confirmOverlap: boolean): Promise<AppointmentOut> {
  const changes = { ...slotChanges(booked, chosen.value), ...noteChanges(booked, chosen.value) };
  return update.run({ id: booked.id, ...changes, confirm_overlap: confirmOverlap });
}

async function saveFollowing(): Promise<void> {
  const booked = props.appointment;
  if (!booked?.recurring_id || !booked.occurrence_date) return;
  const change = seriesChange(booked, chosen.value);
  scopeOpen.value = false;
  failure.value = null;
  try {
    const result = await editSeries.run(change);
    const notesOnly = noteChanges(booked, chosen.value);
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
  if (booked.recurring_id && Object.keys(slotChanges(booked, chosen.value)).length && !confirmOverlap) {
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
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    testid="appointment-form"
    size="xl"
    phone-layout="fullscreen"
    :title="title"
    :submit-label="editing ? $t('appointment.form.save') : $t('appointment.form.create')"
    :pending="pending"
    :error="shown"
    :submit-disabled="!ready || charged"
    @submit="save()"
  >
    <template #default="{ fieldErrors }">
      <div class="appointment-form">
        <div
          class="appointment-form__who"
          data-testid="appointment-form-who"
        >
          <div
            v-if="appointment"
            class="appointment-form__booked"
            data-testid="appointment-form-booked"
          >
            <strong class="appointment-form__booked-name">{{ appointment.customer_name || $t('appointment.list.erasedCustomer') }}</strong>
            <span class="appointment-form__booked-number">
              {{ appointment.number }}
              <StatusPill
                size="sm"
                :tone="STATUS_TONE[appointment.status]"
                :label="$t(`appointment.status.${appointment.status}`)"
              />
            </span>
            <p class="appointment-form__note">
              {{ $t('appointment.form.hint') }}
            </p>
          </div>
          <InlineFeedback
            v-if="charged"
            tone="info"
            data-testid="appointment-form-charged"
          >
            {{ $t('appointment.form.charged') }}
          </InlineFeedback>
          <FieldGroup
            v-if="!editing"
            ref="customerGroup"
            name="customer"
            class="appointment-form__customer"
            data-testid="appointment-form-customer"
          >
            <span class="appointment-form__label">{{ $t('appointment.form.customer') }}</span>
            <CustomerSearch
              :model-value="customer"
              @update:model-value="chooseCustomer"
            />
            <small
              v-if="fieldErrors.customer"
              class="appointment-form__error"
            >{{ fieldErrors.customer }}</small>
          </FieldGroup>
          <div class="appointment-form__services">
            <ServicesField
              v-model="services"
              :facts="facts"
              testid="appointment-form"
              name="services"
              :error-text="fieldErrors.services"
              :disabled="charged"
            />
            <p
              v-if="services.length"
              class="appointment-form__total"
              data-testid="appointment-form-total"
            >
              {{ $t('appointment.form.total') }}: <strong>{{ formatMoney(total, locale, money) }}</strong>
            </p>
          </div>
          <div class="appointment-form__staff">
            <StaffField
              :model-value="staff"
              :service-ids="serviceIds"
              testid="appointment-form"
              name="staff"
              :error-text="fieldErrors.staff"
              :own="!!ownStaff"
              :disabled="charged"
              @update:model-value="pickStaff"
            />
          </div>
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
        </div>
        <div
          class="appointment-form__when"
          data-testid="appointment-form-when"
        >
          <div class="appointment-form__day">
            <DateField
              v-model="day"
              testid="appointment-form-day"
              :label="$t('appointment.form.day')"
              required
              :disabled="charged"
            />
          </div>
          <DurationPicker
            class="appointment-form__duration"
            :minutes="minutes"
            :sum="sumMinutes()"
            :touched="minutesTouched"
            :disabled="charged"
            name="minutes"
            :error-text="fieldErrors.minutes"
            @type="typeMinutes"
            @use-sum="useSum"
          />
          <section class="appointment-form__slots">
            <h3 v-if="!charged">
              {{ $t('appointment.slots.label') }}
            </h3>
            <FreeSlots
              v-if="asking && staff"
              :date="day"
              :service-ids="serviceIds"
              :staff-id="staff.id"
              :staff-name="staff.label"
              :selected="time"
              :today="businessNow.slice(0, 10)"
              :duration-minutes="minutesTouched ? typedMinutes : null"
              :exclude-id="appointment?.id ?? null"
              @pick="time = $event"
              @off="slotsOff = $event"
            />
            <p
              v-else-if="!charged"
              class="appointment-form__unset"
              data-testid="appointment-form-slots-unset"
            >
              <HubIcon
                name="ion:calendar-outline"
                aria-hidden="true"
              />{{ $t('appointment.slots.hint') }}
            </p>
            <div
              v-if="!asking || !slotsOff"
              class="appointment-form__other-time"
              data-testid="appointment-form-other-time"
            >
              <span class="appointment-form__other-label">{{ $t('appointment.form.otherTime') }}</span>
              <TimeField
                v-model="time"
                testid="appointment-form-time"
                :label="$t('appointment.form.time')"
                required
                :disabled="charged"
                name="start"
                :error-text="fieldErrors.start"
              />
            </div>
            <InlineFeedback
              v-if="past"
              tone="warning"
              data-testid="appointment-form-past"
            >
              {{ $t('appointment.form.pastNotice') }}
            </InlineFeedback>
          </section>
        </div>
        <div
          class="appointment-form__more"
          data-testid="appointment-form-more"
        >
          <BookingNotes
            v-model:notes="notes"
            v-model:internal-notes="internalNotes"
            :notes-error="fieldErrors.notes"
            :internal-notes-error="fieldErrors.internal_notes"
          />
          <FoldedSection
            v-if="appointment"
            :title="$t('appointment.form.history')"
            testid="appointment-form-history-fold"
          >
            <AppointmentHistory :appointment-id="appointment.id" />
          </FoldedSection>
        </div>
      </div>
    </template>
    <template #summary>
      <BookingSummary
        :day="day"
        :time="time"
        :minutes="typedMinutes"
        :staff-name="staff?.label ?? ''"
      />
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
/* Phone: one column, the professional and the day side by side. The columns' boxes step aside (`contents`) so their
   fields share the panel's grid, and `dense` brings the day up beside the professional. */
.appointment-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-flow: row dense;
  gap: 14px 10px;
}
.appointment-form__who,
.appointment-form__when {
  display: contents;
}
.appointment-form__who > *,
.appointment-form__when > *,
.appointment-form__more {
  grid-column: 1 / -1;
}
.appointment-form__who > .appointment-form__staff {
  grid-column: 1;
}
.appointment-form__when > .appointment-form__day {
  grid-column: 2;
}
.appointment-form__more,
.appointment-form__slots {
  display: grid;
  gap: 10px;
}
/* Tablet and desktop: who and what on the left, when on the right, the notes under the left column. */
@media (min-width: 640px) {
  .appointment-form {
    grid-template-rows: auto 1fr;
    gap: 14px 24px;
  }
  .appointment-form__who,
  .appointment-form__when {
    display: grid;
    gap: 14px;
    align-content: start;
  }
  .appointment-form__who > *,
  .appointment-form__when > * {
    grid-column: auto;
  }
  .appointment-form__who,
  .appointment-form__more {
    grid-column: 1;
    align-self: start;
  }
  .appointment-form__when {
    grid-column: 2;
    grid-row: 1 / span 2;
    padding-inline-start: 24px;
    border-inline-start: 1px solid var(--ep-border, #d9dde3);
  }
}
.appointment-form__booked {
  display: grid;
  gap: 4px;
}
.appointment-form__booked-name {
  font-size: 1.05rem;
}
.appointment-form__booked-number {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
  color: var(--ep-text-muted, #646b78);
  font-variant-numeric: tabular-nums;
}
.appointment-form__label {
  display: block;
  font-size: 0.85rem;
  color: var(--ep-text-muted, #646b78);
  margin-bottom: 4px;
}
.appointment-form__note {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ep-text-muted, #646b78);
}
.appointment-form__services {
  display: grid;
  gap: 6px;
}
.appointment-form__total {
  display: flex;
  justify-content: space-between;
  margin: 0;
  padding: 0 2px;
  font-size: 0.9rem;
  color: var(--ep-text-muted, #646b78);
}
.appointment-form__total strong {
  color: var(--ion-text-color, #1d2025);
  font-variant-numeric: tabular-nums;
}
.appointment-form__error {
  color: var(--ion-color-danger, #c5000f);
}
.appointment-form__slots h3 {
  margin: 0;
  font-size: 0.95rem;
}
.appointment-form__unset {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  padding: 16px;
  border: 1px dashed var(--ep-border, #d9dde3);
  border-radius: var(--ep-radius-sm, 10px);
  font-size: 0.9rem;
  color: var(--ep-text-muted, #646b78);
}
.appointment-form__unset :deep(svg),
.appointment-form__unset > :first-child {
  flex: none;
  font-size: 22px;
  color: var(--ep-primary-text, #0b5f8a);
}
.appointment-form__other-time {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 150px);
  align-items: center;
  gap: 10px;
  padding-top: 10px;
  border-top: 1px dashed var(--ep-border, #d9dde3);
}
.appointment-form__other-label {
  font-size: 0.9rem;
  color: var(--ep-text-muted, #646b78);
}
</style>
