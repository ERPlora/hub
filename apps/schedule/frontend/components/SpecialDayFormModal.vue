<script setup lang="ts">
// SCHEDULE-F04 «Añadir un día especial» and F13 «Corregir un día especial»: the old «New special day»
// panel as a dialog — Date (a date field: it holds the ISO day), Name, Status («Closed» or «Open (with
// hours)»), the interval editor when open, «Repeats every year» and Notes — and «Add day»; a row opens
// «Edit · {name}» with «Save» (`schedule.special_day.update`). «Add day» waits for a date and a name. A
// line half filled is said in the form; the server's refusal goes under its field and what was typed
// stays.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { blankRows, type IntervalRow, payloadOf, rowsOf } from '../lib/intervals';
import type { SpecialDayOut } from '../operations';
import IntervalsEditor from './IntervalsEditor.vue';

const props = defineProps<{
  /** The special day being corrected; `null` = «New special day». */
  specialDay: SpecialDayOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const date = ref('');
const name = ref('');
const closed = ref(true);
const rows = ref<IntervalRow[]>(blankRows());
const recurring = ref(false);
const notes = ref('');
const incomplete = ref(false);
const creation = useCommand('schedule.special_day.create');
const update = useCommand('schedule.special_day.update');

const editing = computed(() => props.specialDay !== null);
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (editing.value ? update.error.value : creation.error.value));
const title = computed(() =>
  props.specialDay ? t('schedule.specialDays.form.titleEdit', { name: props.specialDay.name }) : t('schedule.specialDays.form.titleNew'),
);
const complete = computed(() => date.value !== '' && name.value.trim() !== '');

watch(
  () => [open.value, props.specialDay?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    const day = props.specialDay;
    date.value = day?.date ?? '';
    name.value = day?.name ?? '';
    closed.value = day?.is_closed ?? true;
    rows.value = day ? rowsOf(day.intervals) : blankRows();
    recurring.value = day?.recurring_yearly ?? false;
    notes.value = day?.notes ?? '';
    incomplete.value = false;
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function save(): Promise<void> {
  if (!complete.value) return;
  const intervals = payloadOf(closed.value, rows.value);
  incomplete.value = intervals === null;
  if (intervals === null) return;
  const fields = {
    date: date.value,
    name: name.value.trim(),
    is_closed: closed.value,
    intervals,
    recurring_yearly: recurring.value,
    notes: notes.value.trim(),
  };
  try {
    if (props.specialDay) await update.run({ id: props.specialDay.id, ...fields });
    else await creation.run(fields);
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="schedule-special-day-form"
    :title="title"
    :submit-label="editing ? $t('schedule.save') : $t('schedule.specialDays.form.submit')"
    :submit-disabled="!complete"
    :pending="pending"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="schedule-exception-form">
        <ion-input
          data-testid="schedule-special-day-form-date"
          type="date"
          :value="date"
          :label="$t('schedule.specialDays.form.date')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.date"
          :class="invalid(fieldErrors.date)"
          @ion-input="date = text($event.detail.value)"
        />
        <ion-input
          data-testid="schedule-special-day-form-name"
          :value="name"
          :label="$t('schedule.specialDays.form.name')"
          :placeholder="$t('schedule.specialDays.form.namePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="name = text($event.detail.value)"
        />
        <ion-select
          data-testid="schedule-special-day-form-status"
          :value="closed ? 'closed' : 'open'"
          :label="$t('schedule.specialDays.form.status')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="closed = $event.detail.value !== 'open'"
        >
          <ion-select-option value="closed">
            {{ $t('schedule.closed') }}
          </ion-select-option>
          <ion-select-option value="open">
            {{ $t('schedule.specialDays.form.openWithHours') }}
          </ion-select-option>
        </ion-select>
        <IntervalsEditor
          v-if="!closed"
          v-model="rows"
          testid="schedule-special-day-form-intervals"
          :error="fieldErrors.intervals"
        />
        <ion-checkbox
          data-testid="schedule-special-day-form-recurring"
          label-placement="end"
          justify="start"
          :checked="recurring"
          @ion-change="recurring = $event.detail.checked"
        >
          {{ $t('schedule.specialDays.form.recurring') }}
        </ion-checkbox>
        <ion-input
          data-testid="schedule-special-day-form-notes"
          :value="notes"
          :label="$t('schedule.specialDays.form.notes')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="1000"
          :error-text="fieldErrors.notes"
          :class="invalid(fieldErrors.notes)"
          @ion-input="notes = text($event.detail.value)"
        />
        <InlineFeedback
          v-if="incomplete"
          tone="danger"
          data-testid="schedule-special-day-form-incomplete"
        >
          {{ $t('schedule.intervals.incomplete') }}
        </InlineFeedback>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.schedule-exception-form {
  display: grid;
  gap: 14px;
}
</style>
