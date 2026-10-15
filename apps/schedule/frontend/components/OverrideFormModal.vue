<script setup lang="ts">
// SCHEDULE-F05 «Añadir un cambio temporal» and F13 «Corregir un cambio temporal»: the old «New override»
// panel as a dialog — From, To (date fields: they hold the ISO day), Reason, Status and the interval
// editor when open — and «Add override»; a row opens «Edit · {reason}» with «Save»
// (`schedule.override.update`). It waits for both dates and a reason. The server's refusal goes under
// its field (another override in those dates under From, an end before the start under To).
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { blankRows, type IntervalRow, payloadOf, rowsOf } from '../lib/intervals';
import type { OverrideOut } from '../operations';
import IntervalsEditor from './IntervalsEditor.vue';

const props = defineProps<{
  /** The override being corrected; `null` = «New override». */
  override: OverrideOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const startDate = ref('');
const endDate = ref('');
const reason = ref('');
const closed = ref(true);
const rows = ref<IntervalRow[]>(blankRows());
const incomplete = ref(false);
const creation = useCommand('schedule.override.create');
const update = useCommand('schedule.override.update');

const editing = computed(() => props.override !== null);
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (editing.value ? update.error.value : creation.error.value));
const title = computed(() =>
  props.override ? t('schedule.overrides.form.titleEdit', { name: props.override.reason }) : t('schedule.overrides.form.titleNew'),
);
const complete = computed(() => startDate.value !== '' && endDate.value !== '' && reason.value.trim() !== '');

watch(
  () => [open.value, props.override?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    const change = props.override;
    startDate.value = change?.start_date ?? '';
    endDate.value = change?.end_date ?? '';
    reason.value = change?.reason ?? '';
    closed.value = change?.is_closed ?? true;
    rows.value = change ? rowsOf(change.intervals) : blankRows();
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
  const fields = { start_date: startDate.value, end_date: endDate.value, reason: reason.value.trim(), is_closed: closed.value, intervals };
  try {
    if (props.override) await update.run({ id: props.override.id, ...fields });
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
    testid="schedule-override-form"
    :title="title"
    :submit-label="editing ? $t('schedule.save') : $t('schedule.overrides.form.submit')"
    :submit-disabled="!complete"
    :pending="pending"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="schedule-exception-form">
        <div class="schedule-exception-form__pair">
          <ion-input
            data-testid="schedule-override-form-start_date"
            type="date"
            :value="startDate"
            :label="$t('schedule.overrides.form.from')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.start_date"
            :class="invalid(fieldErrors.start_date)"
            @ion-input="startDate = text($event.detail.value)"
          />
          <ion-input
            data-testid="schedule-override-form-end_date"
            type="date"
            :value="endDate"
            :label="$t('schedule.overrides.form.to')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.end_date"
            :class="invalid(fieldErrors.end_date)"
            @ion-input="endDate = text($event.detail.value)"
          />
        </div>
        <ion-input
          data-testid="schedule-override-form-reason"
          :value="reason"
          :label="$t('schedule.overrides.form.reason')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.reason"
          :class="invalid(fieldErrors.reason)"
          @ion-input="reason = text($event.detail.value)"
        />
        <ion-select
          data-testid="schedule-override-form-status"
          :value="closed ? 'closed' : 'open'"
          :label="$t('schedule.overrides.form.status')"
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
          testid="schedule-override-form-intervals"
          :error="fieldErrors.intervals"
        />
        <InlineFeedback
          v-if="incomplete"
          tone="danger"
          data-testid="schedule-override-form-incomplete"
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
.schedule-exception-form__pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 10px;
}
</style>
