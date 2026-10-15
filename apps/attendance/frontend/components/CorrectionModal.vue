<script setup lang="ts">
// ATTENDANCE-F08: «Correct working day», the old correction dialog. The clock-in and the clock-out in
// business time (`datetime-local`; an empty clock-out reopens the day) and a mandatory reason. What the
// screen can judge it judges first (a clock-out after the clock-in, a reason of at least 3); the rest
// (an overlap with another day of the person, a second open day, a time in the future) is the server's,
// and its refusal stays here. An untouched time keeps the stored instant to the second; a changed one is
// sent as the business's wall clock, which the server reads in the business's zone.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDay, toLocalInput } from '../lib/time';
import type { RecordOut } from '../operations';

const props = defineProps<{
  /** The day being corrected; `null` while no row asked. */
  record: RecordOut | null;
  /** The person's name heads the dialog when the screen shows the team. */
  team?: boolean;
}>();

const emit = defineEmits<{ corrected: [day: RecordOut] }>();

const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const { run, error, pending } = useCommand('attendance.record.correct');

const clockIn = ref('');
const clockOut = ref('');
const reason = ref('');
const local = ref<Record<string, string>>({});

// Each opening starts from the day as it is.
watch(
  open,
  (isOpen) => {
    if (!isOpen || !props.record) return;
    clockIn.value = toLocalInput(props.record.clock_in_at);
    clockOut.value = props.record.clock_out_at ? toLocalInput(props.record.clock_out_at) : '';
    reason.value = '';
    local.value = {};
    error.value = null;
  },
  { immediate: true },
);

const heading = computed(() => {
  const day = props.record;
  if (!day) return '';
  const parts = [formatDay(day.work_date, locale.value), t(`attendance.status.${day.status}`)];
  return (props.team ? [day.member_name, ...parts] : parts).join(' · ');
});

const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

/** The stored instant when the field still shows it; else what was typed (business wall clock). */
function instant(typed: string, stored: string | null): string {
  return stored && typed === toLocalInput(stored) ? stored : typed;
}

async function save(): Promise<void> {
  const day = props.record;
  if (!day) return;
  const problems: Record<string, string> = {};
  const start = clockIn.value.trim();
  const end = clockOut.value.trim();
  if (!start) problems.clock_in_at = t('attendance.correct.invalidClockIn');
  else if (end && end <= start) problems.clock_out_at = t('attendance.correct.invalidCorrection');
  const why = reason.value.trim();
  if (why.length < 3) problems.reason = t('attendance.correct.reasonRequired');
  local.value = problems;
  if (Object.keys(problems).length) return;
  try {
    const corrected = await run({
      record_id: day.id,
      clock_in_at: instant(start, day.clock_in_at),
      clock_out_at: end ? instant(end, day.clock_out_at) : null,
      reason: why,
    });
    emit('corrected', corrected);
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="attendance-correct"
    :title="$t('attendance.correct.title')"
    :submit-label="$t('attendance.correct.save')"
    submit-icon="ion:create-outline"
    :pending="pending"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <p
        class="attendance-correct__day"
        data-testid="attendance-correct-day"
      >
        {{ heading }}
      </p>
      <ion-input
        data-testid="attendance-correct-clock_in"
        type="datetime-local"
        :value="clockIn"
        :label="$t('attendance.correct.clockIn')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="local.clock_in_at || fieldErrors.clock_in_at"
        :class="invalid(local.clock_in_at || fieldErrors.clock_in_at)"
        @ion-input="clockIn = text($event.detail.value)"
      />
      <ion-input
        data-testid="attendance-correct-clock_out"
        type="datetime-local"
        clear-input
        :value="clockOut"
        :label="$t('attendance.correct.clockOut')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :error-text="local.clock_out_at || fieldErrors.clock_out_at"
        :class="invalid(local.clock_out_at || fieldErrors.clock_out_at)"
        @ion-input="clockOut = text($event.detail.value)"
      />
      <ion-textarea
        data-testid="attendance-correct-reason"
        :value="reason"
        :label="$t('attendance.correct.reason')"
        :helper-text="$t('attendance.correct.reasonHelper')"
        label-placement="floating"
        fill="outline"
        mode="md"
        auto-grow
        counter
        :maxlength="500"
        :error-text="local.reason || fieldErrors.reason"
        :class="invalid(local.reason || fieldErrors.reason)"
        @ion-input="reason = text($event.detail.value)"
      />
    </template>
  </FormModal>
</template>

<style scoped>
.attendance-correct__day {
  margin: 0 0 16px;
  font-weight: 600;
}
ion-input,
ion-textarea {
  margin-bottom: 14px;
}
</style>
