<script setup lang="ts">
// STAFF-F17 «Registrar una ausencia» (`mode="create"`: whoever manages time off registers anyone's,
// picking the Member) and STAFF-F24 «Pedir mi propia ausencia» (`mode="request"`: one's own, no Member).
// The old form: Type (Vacation to begin with), From, To, Full day and, when off, the hours, and
// Reason. The server judges (an overlap is its 409; a bad range, its 422 under the field); the dialog
// keeps what was typed. The new request comes back through the stream, Pending.
import { FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption, IonTextarea, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { LEAVE_TYPES } from '../lib/enums';
import { memberSearch } from '../lib/pickers';
import type { LeaveType, TimeOffFieldsIn } from '../operations';
import SearchSelect from './SearchSelect.vue';

const props = defineProps<{
  /** `create`: anyone's, with Member; `request`: one's own. */
  mode: 'create' | 'request';
}>();

const open = defineModel<boolean>('open', { default: false });

interface TimeOffForm {
  member_id: string;
  member_name: string;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  is_full_day: boolean;
  start_time: string;
  end_time: string;
  reason: string;
}

const blank = (): TimeOffForm => ({
  member_id: '',
  member_name: '',
  leave_type: 'vacation',
  start_date: '',
  end_date: '',
  is_full_day: true,
  start_time: '',
  end_time: '',
  reason: '',
});

const t = useT();
const client = useLiveClient();
const findMembers = memberSearch(client);
const form = ref<TimeOffForm>(blank());
const creation = useCommand('staff.time_off.create');
const request = useCommand('staff.time_off.request');
const forAnyone = computed(() => props.mode === 'create');
const pending = computed(() => creation.pending.value || request.pending.value);
const error = computed(() => (forAnyone.value ? creation.error.value : request.error.value));
const title = computed(() => (forAnyone.value ? t('staff.timeOff.form.titleNew') : t('staff.timeOff.form.titleRequest')));
const complete = computed(() => (!forAnyone.value || form.value.member_id !== '') && form.value.start_date !== '' && form.value.end_date !== '');

watch(open, (isOpen) => {
  if (!isOpen) return;
  form.value = blank();
  creation.error.value = null;
  request.error.value = null;
});

function set<K extends keyof TimeOffForm>(field: K, value: TimeOffForm[K]): void {
  form.value = { ...form.value, [field]: value };
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

/** The absence as the server takes it: the hours only for part of a day. */
function fields(): TimeOffFieldsIn {
  const f = form.value;
  return {
    leave_type: f.leave_type,
    start_date: f.start_date,
    end_date: f.end_date,
    is_full_day: f.is_full_day,
    ...(f.is_full_day ? {} : { start_time: f.start_time || null, end_time: f.end_time || null }),
    reason: f.reason.trim(),
  };
}

async function save(): Promise<void> {
  try {
    if (forAnyone.value) await creation.run({ member_id: form.value.member_id, ...fields() });
    else await request.run(fields());
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="staff-time-off-form"
    :title="title"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="staff-time-off-form">
        <SearchSelect
          v-if="forAnyone"
          testid="staff-time-off-form-member_id"
          :value="form.member_id"
          :display="form.member_name"
          :label="$t('staff.timeOff.form.member')"
          :load="findMembers"
          :error-text="fieldErrors.member_id ?? fieldErrors.member"
          @update:value="(value: string, label: string) => (form = { ...form, member_id: value, member_name: label })"
        />
        <ion-select
          data-testid="staff-time-off-form-leave_type"
          :value="form.leave_type"
          :label="$t('staff.timeOff.form.type')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.leave_type"
          :class="invalid(fieldErrors.leave_type)"
          @ion-change="set('leave_type', ($event.detail.value || 'vacation') as LeaveType)"
        >
          <ion-select-option
            v-for="type in LEAVE_TYPES"
            :key="type"
            :value="type"
          >
            {{ $t(`staff.leaveType.${type}`) }}
          </ion-select-option>
        </ion-select>
        <div class="staff-time-off-form__pair">
          <ion-input
            data-testid="staff-time-off-form-start_date"
            type="date"
            :value="form.start_date"
            :label="$t('staff.timeOff.form.startDate')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.start_date"
            :class="invalid(fieldErrors.start_date)"
            @ion-input="set('start_date', text($event.detail.value))"
          />
          <ion-input
            data-testid="staff-time-off-form-end_date"
            type="date"
            :value="form.end_date"
            :label="$t('staff.timeOff.form.endDate')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.end_date"
            :class="invalid(fieldErrors.end_date)"
            @ion-input="set('end_date', text($event.detail.value))"
          />
        </div>
        <ion-toggle
          data-testid="staff-time-off-form-is_full_day"
          label-placement="end"
          justify="start"
          :checked="form.is_full_day"
          @ion-change="set('is_full_day', $event.detail.checked)"
        >
          {{ $t('staff.timeOff.form.fullDay') }}
        </ion-toggle>
        <div
          v-if="!form.is_full_day"
          class="staff-time-off-form__pair"
        >
          <ion-input
            data-testid="staff-time-off-form-start_time"
            type="time"
            :value="form.start_time"
            :label="$t('staff.timeOff.form.startTime')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.start_time"
            :class="invalid(fieldErrors.start_time)"
            @ion-input="set('start_time', text($event.detail.value))"
          />
          <ion-input
            data-testid="staff-time-off-form-end_time"
            type="time"
            :value="form.end_time"
            :label="$t('staff.timeOff.form.endTime')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.end_time"
            :class="invalid(fieldErrors.end_time)"
            @ion-input="set('end_time', text($event.detail.value))"
          />
        </div>
        <ion-textarea
          data-testid="staff-time-off-form-reason"
          :value="form.reason"
          :label="$t('staff.timeOff.form.reason')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="500"
          :auto-grow="true"
          :error-text="fieldErrors.reason"
          :class="invalid(fieldErrors.reason)"
          @ion-input="set('reason', text($event.detail.value))"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-time-off-form {
  display: grid;
  gap: 14px;
}
.staff-time-off-form__pair {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 10px;
}
</style>
