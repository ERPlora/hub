<script setup lang="ts">
// SCHEDULE-F02 «Fijar el horario de un día»: the old «Edit hours — {day}» panel as a dialog — Day,
// Closed, Open 24 hours and the interval editor (a day not set starts from 09:00–18:00, as the old
// panel did) — and «Save day», which sends `schedule.week.set_day`: the day's intervals are replaced.
// Another day in the selector re-titles the dialog and saves what is typed there (the old panel's way to
// copy a day). A line half filled is said in the form and nothing is sent; the server's refusal of the
// intervals goes under them, and what was typed stays.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonCheckbox, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { ALL_DAY, type IntervalRow, isAllDay, payloadOf, rowsOf } from '../lib/intervals';
import type { WeekDayOut } from '../operations';
import IntervalsEditor from './IntervalsEditor.vue';

const props = defineProps<{
  /** The day being edited. */
  day: WeekDayOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const WEEK = [0, 1, 2, 3, 4, 5, 6] as const;
/** Where a day that was never set starts: the old panel's 09:00–18:00. */
const DEFAULT_ROWS: IntervalRow[] = [{ open_time: '09:00', close_time: '18:00' }];

const weekday = ref(0);
const closed = ref(false);
const rows = ref<IntervalRow[]>([...DEFAULT_ROWS]);
const incomplete = ref(false);
const saving = useCommand('schedule.week.set_day');

const title = computed(() => t('schedule.hours.form.title', { day: t(`schedule.days.${weekday.value}`) }));
const allDay = computed(() => isAllDay(rows.value));

watch(
  () => [open.value, props.day] as const,
  ([isOpen, day]) => {
    if (!isOpen || !day) return;
    weekday.value = day.weekday;
    closed.value = day.is_closed;
    rows.value = day.is_set && day.intervals.length ? rowsOf(day.intervals) : [...DEFAULT_ROWS];
    incomplete.value = false;
    saving.error.value = null;
  },
  { immediate: true },
);

function setAllDay(checked: boolean): void {
  rows.value = checked ? [{ ...ALL_DAY }] : [...DEFAULT_ROWS];
  incomplete.value = false;
}

function setClosed(checked: boolean): void {
  closed.value = checked;
  incomplete.value = false;
}

async function save(): Promise<void> {
  const intervals = payloadOf(closed.value, rows.value);
  incomplete.value = intervals === null;
  if (intervals === null) return;
  try {
    await saving.run({ weekday: weekday.value, is_closed: closed.value, intervals });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="schedule-day-form"
    :title="title"
    :submit-label="$t('schedule.hours.form.submit')"
    :pending="saving.pending.value"
    :error="saving.error.value"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="schedule-day-form">
        <ion-select
          data-testid="schedule-day-form-weekday"
          :value="weekday"
          :label="$t('schedule.hours.form.day')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="weekday = Number($event.detail.value)"
        >
          <ion-select-option
            v-for="value in WEEK"
            :key="value"
            :value="value"
          >
            {{ $t(`schedule.days.${value}`) }}
          </ion-select-option>
        </ion-select>
        <ion-checkbox
          data-testid="schedule-day-form-closed"
          label-placement="end"
          justify="start"
          :checked="closed"
          @ion-change="setClosed($event.detail.checked)"
        >
          {{ $t('schedule.hours.form.closed') }}
        </ion-checkbox>
        <template v-if="!closed">
          <ion-checkbox
            data-testid="schedule-day-form-open24h"
            label-placement="end"
            justify="start"
            :checked="allDay"
            @ion-change="setAllDay($event.detail.checked)"
          >
            {{ $t('schedule.hours.form.open24h') }}
          </ion-checkbox>
          <IntervalsEditor
            v-if="!allDay"
            v-model="rows"
            testid="schedule-day-form-intervals"
            :error="fieldErrors.intervals"
          />
        </template>
        <InlineFeedback
          v-if="incomplete"
          tone="danger"
          data-testid="schedule-day-form-incomplete"
        >
          {{ $t('schedule.intervals.incomplete') }}
        </InlineFeedback>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.schedule-day-form {
  display: grid;
  gap: 14px;
}
</style>
