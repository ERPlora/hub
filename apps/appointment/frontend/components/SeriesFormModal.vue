<script setup lang="ts">
// APPOINTMENT-F12, F14: the repeating appointment's panel. «New repeating appointment»: Customer, Services,
// Professional (only who does them all), Repeats, Day of the week (weekly and fortnightly only), Starts on,
// Time, Min. (the services' sum unless typed), «Ends on (optional)» and «Number of appointments
// (optional)»; «Create repeating appointment» creates it and books its window (the page shows what was
// booked and skipped). «Edit repeating appointment»: the change applies from a date on («From») — the
// panel says how many booked appointments it reaches and how many charged ones it leaves alone — and
// «Save from this occurrence on» sends only what changed.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useT } from '../composables/useT';
import { eligibleStaff, ownTerms, type ServiceFacts } from '../lib/pickers';
import type { Frequency, MaterializeOut, RecurringCreateIn, RecurringOut, RecurringUpdatedOut, RecurringUpdateIn } from '../operations';
import SeriesScopeHint from './SeriesScopeHint.vue';
import ServicesField from './ServicesField.vue';

const FREQUENCIES: readonly Frequency[] = ['daily', 'weekly', 'biweekly', 'monthly'];
const WEEKDAYS = [0, 1, 2, 3, 4, 5, 6] as const;

const props = withDefaults(
  defineProps<{
    series: RecurringOut | null;
    businessToday: string;
    /** Edit: the occurrence the change applies from (today by default). */
    fromDate?: string | null;
    ownStaff?: { id: string; name: string } | null;
  }>(),
  { fromDate: null, ownStaff: null },
);

const emit = defineEmits<{ outcome: [outcome: MaterializeOut]; updated: [outcome: RecurringUpdatedOut] }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const client = useLiveClient();
const facts = new Map<string, ServiceFacts>();

const customer = ref<CustomerSnapshot | null>(null);
const services = ref<ComboOption[]>([]);
const staff = ref<ComboOption | null>(null);
const frequency = ref<Frequency>('weekly');
const weekday = ref<number | null>(null);
const startDate = ref('');
const from = ref('');
const time = ref('');
const minutes = ref('');
const minutesTouched = ref(false);
const endDate = ref('');
const occurrences = ref('');

const create = useCommand('appointment.recurring.create');
const update = useCommand('appointment.recurring.update');
const pending = computed(() => create.pending.value || update.pending.value);
const error = computed(() => (props.series ? update.error.value : create.error.value));
const editing = computed(() => props.series !== null);
const weekly = computed(() => frequency.value === 'weekly' || frequency.value === 'biweekly');
const serviceIds = computed(() => services.value.map((option) => option.id));
const searchStaff = (query: string) => eligibleStaff(client, serviceIds.value, query);

const ready = computed(
  () =>
    (editing.value || (!!customer.value && services.value.length > 0 && !!staff.value && !!startDate.value)) && !!time.value,
);

const hhmm = (value: string): string => value.slice(0, 5);
const whole = (value: string): number | null => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : null);

function reset(): void {
  const series = props.series;
  create.error.value = null;
  update.error.value = null;
  minutesTouched.value = false;
  customer.value = null;
  if (series) {
    for (const line of series.services) facts.set(line.service_id, { name: line.name, minutes: 0, price: 0 });
    services.value = series.services.map((line) => ({ id: line.service_id, label: line.name }));
    staff.value = series.staff_id ? { id: series.staff_id, label: series.staff_name } : null;
    frequency.value = series.frequency;
    weekday.value = series.day_of_week;
    startDate.value = series.start_date;
    from.value = props.fromDate ?? (series.start_date > props.businessToday ? series.start_date : props.businessToday);
    time.value = hhmm(series.time);
    minutes.value = String(series.duration_minutes);
    endDate.value = series.end_date ?? '';
    occurrences.value = series.max_occurrences ? String(series.max_occurrences) : '';
    return;
  }
  services.value = [];
  staff.value = props.ownStaff ? { id: props.ownStaff.id, label: props.ownStaff.name } : null;
  frequency.value = 'weekly';
  weekday.value = null;
  startDate.value = props.businessToday;
  from.value = '';
  time.value = '';
  minutes.value = '';
  endDate.value = '';
  occurrences.value = '';
}

watch(
  () => [open.value, props.series?.id] as const,
  ([isOpen]) => {
    if (isOpen) reset();
  },
  { immediate: true },
);

/** Number of the last question for the professional's terms: an older answer is dropped. */
let asked = 0;

// A new series proposes the services' minutes as its professional does them (her own, else the
// catalog's), unless typed: what the server books.
watch(
  () => `${staff.value?.id ?? ''}|${serviceIds.value.join()}`,
  async () => {
    if (minutesTouched.value || editing.value) return;
    const mine = ++asked;
    const catalog = (id: string) => facts.get(id)?.minutes ?? 0;
    let own = new Map<string, { minutes: number }>();
    if (staff.value && serviceIds.value.length) {
      try {
        own = await ownTerms(client, staff.value.id, serviceIds.value);
      } catch {
        // The catalog's stay; the server books her own anyway.
      }
    }
    if (mine !== asked || minutesTouched.value || editing.value) return;
    const sum = serviceIds.value.reduce((acc, id) => acc + (own.get(id)?.minutes ?? catalog(id)), 0);
    minutes.value = sum ? String(sum) : '';
  },
);

function newSeries(): RecurringCreateIn {
  const out: RecurringCreateIn = {
    customer_id: customer.value?.customer_id ?? null,
    services: serviceIds.value.map((id) => ({ service_id: id })),
    staff_id: staff.value?.id ?? null,
    frequency: frequency.value,
    start_date: startDate.value,
    time: hhmm(time.value),
  };
  if (weekly.value && weekday.value !== null) out.day_of_week = weekday.value;
  if (minutesTouched.value && whole(minutes.value)) out.duration_minutes = whole(minutes.value);
  if (endDate.value) out.end_date = endDate.value;
  if (whole(occurrences.value)) out.max_occurrences = whole(occurrences.value);
  return out;
}

function changes(series: RecurringOut): RecurringUpdateIn {
  const out: RecurringUpdateIn = { id: series.id, from_date: from.value || props.businessToday };
  if (frequency.value !== series.frequency) out.frequency = frequency.value;
  if (weekly.value && weekday.value !== series.day_of_week && weekday.value !== null) out.day_of_week = weekday.value;
  if (hhmm(time.value) !== hhmm(series.time)) out.time = hhmm(time.value);
  if (whole(minutes.value) && whole(minutes.value) !== series.duration_minutes) out.duration_minutes = whole(minutes.value);
  if (staff.value && staff.value.id !== series.staff_id) out.staff_id = staff.value.id;
  if (serviceIds.value.join() !== series.services.map((line) => line.service_id).join()) {
    out.services = serviceIds.value.map((id) => ({ service_id: id }));
  }
  if ((endDate.value || null) !== series.end_date) out.end_date = endDate.value || null;
  if ((whole(occurrences.value) ?? null) !== series.max_occurrences && whole(occurrences.value)) {
    out.max_occurrences = whole(occurrences.value);
  }
  return out;
}

async function save(): Promise<void> {
  try {
    if (props.series) emit('updated', await update.run(changes(props.series)));
    else emit('outcome', await create.run(newSeries()));
  } catch {
    return; // The panel says why; what was typed stays.
  }
  open.value = false;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="series-form"
    :title="editing ? $t('appointment.series.form.titleEdit') : $t('appointment.series.form.titleNew')"
    :submit-label="editing ? $t('appointment.series.form.save') : $t('appointment.series.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!ready"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="series-form">
        <p
          v-if="series"
          class="series-form__who"
        >
          {{ series.customer_name || $t('appointment.list.erasedCustomer') }}
        </p>
        <div v-else>
          <span class="series-form__label">{{ $t('appointment.form.customer') }}</span>
          <CustomerSearch v-model="customer" />
        </div>
        <ServicesField
          v-model="services"
          :facts="facts"
          testid="series-form"
          :error-text="fieldErrors.services"
        />
        <Combo
          testid="series-form-staff"
          :model-value="staff"
          :search="searchStaff"
          :label="t('appointment.form.staff')"
          :placeholder="t('appointment.form.pickStaff')"
          :empty-label="t('appointment.form.staffNone')"
          :error-text="fieldErrors.staff"
          :clearable="!ownStaff"
          :disabled="!!ownStaff"
          @update:model-value="staff = $event"
        />
        <ion-input
          v-if="series"
          data-testid="series-form-from_date"
          type="date"
          :value="from"
          :label="$t('appointment.series.form.fromDate')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.from_date"
          @ion-input="from = text($event.detail.value)"
        />
        <SeriesScopeHint
          v-if="series"
          :series-id="series.id"
          :from-date="from || businessToday"
        />
        <div class="series-form__grid">
          <ion-select
            data-testid="series-form-frequency"
            :value="frequency"
            :label="$t('appointment.series.form.frequency')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="frequency = $event.detail.value as Frequency"
          >
            <ion-select-option
              v-for="option in FREQUENCIES"
              :key="option"
              :value="option"
            >
              {{ t(`appointment.series.frequency.${option}`) }}
            </ion-select-option>
          </ion-select>
          <ion-select
            v-if="weekly"
            data-testid="series-form-weekday"
            :value="weekday"
            :label="$t('appointment.series.form.weekday')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            @ion-change="weekday = Number($event.detail.value)"
          >
            <ion-select-option
              v-for="day in WEEKDAYS"
              :key="day"
              :value="day"
            >
              {{ t(`appointment.weekday.${day}`) }}
            </ion-select-option>
          </ion-select>
          <ion-input
            v-if="!series"
            data-testid="series-form-start_date"
            type="date"
            :value="startDate"
            :label="$t('appointment.series.form.startDate')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.start_date"
            @ion-input="startDate = text($event.detail.value)"
          />
          <ion-input
            data-testid="series-form-time"
            type="time"
            :value="time"
            :label="$t('appointment.series.form.time')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.time"
            @ion-input="time = text($event.detail.value)"
          />
          <ion-input
            data-testid="series-form-minutes"
            type="number"
            inputmode="numeric"
            min="1"
            :value="minutes"
            :label="$t('appointment.series.form.minutes')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.duration_minutes"
            @ion-input="(minutes = text($event.detail.value)), (minutesTouched = true)"
          />
          <ion-input
            data-testid="series-form-end_date"
            type="date"
            :value="endDate"
            :label="$t('appointment.series.form.endDate')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.end_date"
            @ion-input="endDate = text($event.detail.value)"
          />
          <ion-input
            data-testid="series-form-max_occurrences"
            type="number"
            inputmode="numeric"
            min="1"
            :value="occurrences"
            :label="$t('appointment.series.form.occurrences')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.max_occurrences"
            @ion-input="occurrences = text($event.detail.value)"
          />
        </div>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.series-form {
  display: grid;
  gap: 14px;
}
.series-form__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.series-form__label {
  display: block;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b7280);
  margin-bottom: 4px;
}
.series-form__who {
  margin: 0;
  font-weight: 600;
}
</style>
