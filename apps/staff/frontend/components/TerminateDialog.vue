<script setup lang="ts">
// STAFF-F06 «Dar de baja a un profesional»: the old confirmation with its two inputs — «Last day
// (today if empty)» and «Reason (optional)» — as a consequential dialog (alertdialog, red action). It
// sends `staff.member.terminate`; the day only when given (the server takes today in the business's
// calendar). The termination is final; the person disappears from the list through the stream.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonInput, IonTextarea } from '@ionic/vue';
import { ref, watch } from 'vue';

import type { MemberOut, TerminateIn } from '../operations';

const props = defineProps<{
  /** Who leaves; `null` while no row asked. */
  member: MemberOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

const lastDay = ref('');
const reason = ref('');
const { run, error, pending } = useCommand('staff.member.terminate');

watch(open, (isOpen) => {
  if (!isOpen) return;
  lastDay.value = '';
  reason.value = '';
  error.value = null;
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

async function terminate(): Promise<void> {
  const member = props.member;
  if (!member) return;
  const input: TerminateIn = { id: member.id, reason: reason.value.trim() };
  if (lastDay.value) input.termination_date = lastDay.value;
  try {
    await run(input);
  } catch {
    return; // The dialog paints the error.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="staff-member-terminate"
    size="sm"
    role="alertdialog"
    submit-color="danger"
    submit-icon="ion:person-remove-outline"
    :title="$t('staff.members.terminate.title')"
    :submit-label="$t('staff.members.terminate.confirm')"
    :pending="pending"
    :error="error"
    @submit="terminate"
  >
    <template #default="{ fieldErrors }">
      <div class="staff-terminate">
        <p
          class="staff-terminate__message"
          data-testid="staff-member-terminate-message"
        >
          {{ $t('staff.members.terminate.message', { name: member?.full_name ?? '' }) }}
        </p>
        <ion-input
          data-testid="staff-member-terminate-termination_date"
          type="date"
          :value="lastDay"
          :label="$t('staff.members.terminate.date')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.termination_date"
          :class="invalid(fieldErrors.termination_date)"
          @ion-input="lastDay = text($event.detail.value)"
        />
        <ion-textarea
          data-testid="staff-member-terminate-reason"
          :value="reason"
          :label="$t('staff.members.terminate.reason')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="500"
          :auto-grow="true"
          :error-text="fieldErrors.reason"
          :class="invalid(fieldErrors.reason)"
          @ion-input="reason = text($event.detail.value)"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.staff-terminate {
  display: grid;
  gap: 14px;
}
.staff-terminate__message {
  margin: 0;
  line-height: 1.45;
}
</style>
