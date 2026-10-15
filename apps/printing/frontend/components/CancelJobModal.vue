<script setup lang="ts">
// «Cancel Receipt T-000123?» (PRINTING-F14; the old «Discard»): it will not be printed and stays in the
// queue with who cancelled it and why; «Reason (optional)»; «Yes, cancel» (danger) and «Back». The server
// says when a job can no longer be cancelled (a device is printing it, or it printed).
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { jobTitle } from '../lib/format';
import { refusal } from '../lib/refusal';
import type { JobOut } from '../operations';

const props = defineProps<{ job: JobOut | null }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const locale = useLocale();
const cancel = useCommand('printing.job.cancel');
const reason = shallowRef('');

watch(
  open,
  (now) => {
    if (!now) return;
    reason.value = '';
    cancel.error.value = null;
  },
  { immediate: true },
);

const title = computed(() => (props.job ? t('printing.jobs.cancel.title', { job: jobTitle(props.job, t, locale.value) }) : ''));
const error = computed<FormModalError | null>(() => refusal(cancel.error.value, t('printing.jobs.cancel.failed')));

async function confirm(): Promise<void> {
  if (!props.job) return;
  try {
    await cancel.run({ job_id: props.job.id, reason: reason.value.trim() });
  } catch {
    return; // The window shows the refusal.
  }
  void toastSuccess(t('printing.jobs.cancel.done'));
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    size="sm"
    role="alertdialog"
    phone-layout="card"
    submit-color="danger"
    testid="printing-cancel-job"
    :title="title"
    :submit-label="$t('printing.jobs.cancel.confirm')"
    :cancel-label="$t('printing.jobs.cancel.back')"
    :pending="cancel.pending.value"
    :error="error"
    @submit="confirm"
  >
    <div class="printing-cancel">
      <p data-testid="printing-cancel-job-body">
        {{ $t('printing.jobs.cancel.body') }}
      </p>
      <ion-textarea
        data-testid="printing-cancel-job-reason"
        :label="$t('printing.jobs.cancel.reason')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="500"
        :auto-grow="true"
        :value="reason"
        @ion-input="reason = String($event.detail.value ?? '')"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.printing-cancel {
  display: grid;
  gap: 12px;
}
.printing-cancel p {
  margin: 0;
}
</style>
