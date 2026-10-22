<script setup lang="ts">
// STAFF-F13 «Crear el horario semanal» and STAFF-F14 «Editar un horario»: the old panel as a dialog —
// Schedule (name; empty, the server's «Regular schedule»), Effective from, Effective until, Default and
// the week, one row per weekday: «works» and Start «to» End «break» Start «to» End, or «Off». New
// proposes Monday to Friday with the business's default working day (`staff.settings.get`, followed
// live; until it arrives, its own defaults) and sends `staff.schedule.create` for the member; editing sends
// `staff.schedule.update`, which replaces the whole week. The server judges: a day's problem goes under
// that day's row (its `days.<i>` named back to the weekday), a week without working days on the week.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonCheckbox, IonInput } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import {
  blankScheduleForm,
  dayErrors,
  daysPayload,
  DEFAULT_WORKDAY,
  type ScheduleForm,
  scheduleFormFromRecord,
  type WeekRow,
  workdayFromSettings,
} from '../lib/scheduleForm';
import type { DayIn, ScheduleOut } from '../operations';

const props = withDefaults(
  defineProps<{
    /** Whose schedule. */
    memberId: string;
    /** The schedule being edited; `null` = «New». */
    schedule: ScheduleOut | null;
    /** A new one starts as «Default»: only when the member has no default schedule yet. */
    proposeDefault?: boolean;
  }>(),
  { proposeDefault: true },
);

const open = defineModel<boolean>('open', { default: false });

const t = useT();
/** The business's default working day (Staff › Settings, STAFF-F22): what a new week proposes. */
const { data: settings } = useLive('staff.settings.get', {});
const workday = computed(() => (settings.value ? workdayFromSettings(settings.value) : DEFAULT_WORKDAY));
const form = ref<ScheduleForm>(blankScheduleForm({ isDefault: true }));
/** The days of the last save: the server names a day by its position among them. */
const sentDays = shallowRef<DayIn[]>([]);
const creation = useCommand('staff.schedule.create');
const update = useCommand('staff.schedule.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.schedule ? update.error.value : creation.error.value));
const errorsByDay = computed(() => dayErrors(error.value?.fields ?? {}, sentDays.value));
const title = computed(() => (props.schedule ? t('staff.schedules.form.titleEdit', { name: props.schedule.name }) : t('staff.schedules.form.titleNew')));

watch(
  () => [open.value, props.schedule?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = props.schedule
      ? scheduleFormFromRecord(props.schedule, workday.value)
      : blankScheduleForm({ isDefault: props.proposeDefault, workday: workday.value });
    sentDays.value = [];
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function setDay(weekday: number, change: Partial<WeekRow>): void {
  form.value = { ...form.value, week: form.value.week.map((day) => (day.weekday === weekday ? { ...day, ...change } : day)) };
}

async function save(): Promise<void> {
  const f = form.value;
  const days = daysPayload(f.week);
  sentDays.value = days;
  const common = {
    name: f.name.trim(),
    is_default: f.is_default,
    effective_from: f.effective_from || null,
    effective_until: f.effective_until || null,
    days,
  };
  try {
    if (props.schedule) await update.run({ id: props.schedule.id, ...common });
    else await creation.run({ member_id: props.memberId, ...common });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}

/** The four hour fields of a working day. */
const HOURS = [
  { part: 'start', key: 'start', label: 'staff.schedules.form.start', after: 'staff.schedules.form.sepTo' },
  { part: 'end', key: 'end', label: 'staff.schedules.form.end', after: 'staff.schedules.form.sepBreak' },
  { part: 'break_start', key: 'breakStart', label: 'staff.schedules.form.breakStart', after: 'staff.schedules.form.sepTo' },
  { part: 'break_end', key: 'breakEnd', label: 'staff.schedules.form.breakEnd', after: '' },
] as const;
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="staff-schedule-form"
    :title="title"
    :submit-label="schedule ? $t('staff.save') : $t('staff.schedules.form.create')"
    :pending="pending"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="staff-schedule-form">
        <ion-input
          data-testid="staff-schedule-form-name"
          :value="form.name"
          :label="$t('staff.schedules.form.name')"
          :placeholder="$t('staff.schedules.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <div class="staff-schedule-form__pair">
          <ion-input
            data-testid="staff-schedule-form-effective_from"
            type="date"
            :value="form.effective_from"
            :label="$t('staff.schedules.form.effectiveFrom')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.effective_from"
            :class="invalid(fieldErrors.effective_from)"
            @ion-input="form = { ...form, effective_from: text($event.detail.value) }"
          />
          <ion-input
            data-testid="staff-schedule-form-effective_until"
            type="date"
            :value="form.effective_until"
            :label="$t('staff.schedules.form.effectiveUntil')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.effective_until"
            :class="invalid(fieldErrors.effective_until)"
            @ion-input="form = { ...form, effective_until: text($event.detail.value) }"
          />
        </div>
        <ion-checkbox
          data-testid="staff-schedule-form-is_default"
          label-placement="end"
          justify="start"
          :checked="form.is_default"
          @ion-change="form = { ...form, is_default: $event.detail.checked }"
        >
          {{ $t('staff.schedules.form.isDefault') }}
        </ion-checkbox>
        <fieldset class="staff-week">
          <legend class="staff-week__legend">
            {{ $t('staff.schedules.form.week') }}
          </legend>
          <InlineFeedback
            v-if="fieldErrors.days"
            tone="danger"
            data-testid="staff-schedule-form-week-error"
          >
            {{ fieldErrors.days }}
          </InlineFeedback>
          <div
            v-for="day in form.week"
            :key="day.weekday"
            class="staff-week__day"
            :data-testid="`staff-schedule-form-day-${day.weekday}`"
          >
            <ion-checkbox
              :data-testid="`staff-schedule-form-day-${day.weekday}-working`"
              class="staff-week__name"
              label-placement="end"
              justify="start"
              :checked="day.working"
              @ion-change="setDay(day.weekday, { working: $event.detail.checked })"
            >
              {{ $t(`staff.days.long.${day.weekday}`) }}
            </ion-checkbox>
            <div
              v-if="day.working"
              class="staff-week__hours"
            >
              <template
                v-for="hour in HOURS"
                :key="hour.part"
              >
                <ion-input
                  :data-testid="`staff-schedule-form-day-${day.weekday}-${hour.part}`"
                  class="staff-week__time"
                  type="time"
                  :value="day[hour.key]"
                  :label="$t(hour.label)"
                  label-placement="stacked"
                  fill="outline"
                  mode="md"
                  @ion-input="setDay(day.weekday, { [hour.key]: text($event.detail.value) })"
                />
                <span
                  v-if="hour.after"
                  class="staff-week__sep"
                >{{ $t(hour.after) }}</span>
              </template>
            </div>
            <span
              v-else
              class="staff-week__sep"
              :data-testid="`staff-schedule-form-day-${day.weekday}-off`"
            >{{ $t('staff.schedules.form.notWorking') }}</span>
            <p
              v-if="errorsByDay[day.weekday]"
              class="staff-week__error"
              :data-testid="`staff-schedule-form-day-${day.weekday}-error`"
            >
              {{ errorsByDay[day.weekday] }}
            </p>
          </div>
        </fieldset>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-schedule-form {
  display: grid;
  gap: 14px;
}
.staff-schedule-form__pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 10px;
}
.staff-week {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  border: 0;
}
.staff-week__legend {
  padding: 0;
  margin-bottom: 4px;
  font-weight: 600;
}
.staff-week__day {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 10px;
  padding-top: 8px;
  border-top: 1px solid var(--ion-border-color, #e5e3dd);
}
/* The day's name is the checkbox label: clickable, and the accessible name of the box. */
.staff-week__name {
  width: 7.5rem;
  font-weight: 600;
}
.staff-week__name::part(label) {
  white-space: normal;
}
.staff-week__hours {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.staff-week__time {
  width: 7.5rem;
}
.staff-week__sep {
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
}
.staff-week__error {
  flex-basis: 100%;
  margin: 0;
  color: var(--ion-color-danger, #c5000f);
  font-size: 0.85rem;
}
</style>
