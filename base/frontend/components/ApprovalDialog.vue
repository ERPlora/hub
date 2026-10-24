<script setup lang="ts">
// «An approval is needed» (BASE-G136; the old hub's HUB_SHELL-F51; Square's and Toast's manager override), opened by
// `withApproval` (lib/approval.ts) over the screen where the action was refused: what is approved in the app's words,
// «Who approves it?» with the people of the business who may do it themselves and have a PIN (live
// `base.approval.approvers`), on the till's faces and PIN pad (APP-BASE-3's PinDoor), or their badge swiped at any
// moment (APP-BASE-3's reader). An approval closes the dialog with the pass and says «Approved by <name>»; a refusal
// stays here, told from its code; «Cancel» closes it with none, and the app tells the original refusal. From a tablet up
// the dialog is as tall as its whole pad (the styles at the end), never Ionic's fixed card, which cut its last row.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonButtons, IonHeader, IonSpinner, IonTitle, IonToolbar, modalController } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { createBadgeReader } from '../lib/access';
import { APPROVED, type ApprovalQuestion } from '../lib/approval';
import { useBaseI18n } from '../lib/i18n';
import type { ApprovalInput } from '../operations';
import PinDoor from './PinDoor.vue';

const props = defineProps<{ question: ApprovalQuestion }>();

const { t } = useBaseI18n();
const { data, status, refresh } = useLive('base.approval.approvers', { operation: props.question.operation });
const approve = useCommand('base.approval.approve');

const people = computed(() => data.value?.people ?? []);
const pinLength = computed(() => data.value?.pin_length ?? 4);
const loading = computed(() => data.value === undefined && status.value !== 'error');
const failed = computed(() => data.value === undefined && status.value === 'error');
const action = computed(() => props.question.label || t('base.approval.unnamed'));
const busy = ref(false);
const error = ref('');

const REFUSALS: Record<string, string> = {
  'base.approval_refused': 'base.approval.errors.refused',
  'base.approver_cannot': 'base.approval.errors.cannot',
  'base.approval_not_needed': 'base.approval.errors.notNeeded',
  'base.approval_not_offered': 'base.approval.errors.notOffered',
};

/** A refusal in this person's words: from its code; the brake's own, which says how long to wait. */
function refusalOf(failure: unknown): string {
  if (failure instanceof ApiError) {
    if (failure.code === 'base.too_many_attempts') return failure.message;
    const key = REFUSALS[failure.code];
    if (key) return t(key);
  }
  return t('base.approval.errors.failed');
}

async function send(entry: { person: string; pin: string } | { badge: string }): Promise<void> {
  if (busy.value) return;
  busy.value = true;
  error.value = '';
  const input: ApprovalInput = { operation: props.question.operation, fingerprint: props.question.fingerprint, ...entry };
  try {
    const pass = await approve.run(input);
    void toastSuccess(t('base.approval.approvedBy', { name: pass.approver }));
    await modalController.dismiss(pass.token, APPROVED);
  } catch (failure) {
    error.value = refusalOf(failure);
  } finally {
    busy.value = false;
  }
}

function cancel(): void {
  void modalController.dismiss(null, 'cancel');
}

let stopReader: () => void = () => {};
onMounted(() => {
  stopReader = createBadgeReader((badge) => void send({ badge }));
});
onBeforeUnmount(() => stopReader());
</script>

<template>
  <IonHeader>
    <IonToolbar>
      <IonTitle>{{ t('base.approval.title') }}</IonTitle>
      <IonButtons slot="end">
        <IonButton
          data-testid="approval-cancel"
          @click="cancel"
        >
          {{ t('base.approval.cancel') }}
        </IonButton>
      </IonButtons>
    </IonToolbar>
  </IonHeader>
  <div class="approval-dialog__body ion-padding">
    <div class="approval-dialog">
      <p
        class="approval-dialog__action"
        data-testid="approval-action"
      >
        {{ t('base.approval.approving', { action }) }}
      </p>
      <p class="approval-dialog__hint">
        {{ t('base.approval.askPin') }}
        <br>
        {{ t('base.approval.orBadge') }}
      </p>
      <IonSpinner
        v-if="loading"
        name="crescent"
        data-testid="approval-loading"
      />
      <InlineFeedback
        v-else-if="failed"
        tone="danger"
        data-testid="approval-failed"
      >
        {{ t('base.approval.loadFailed') }}
        <template #actions>
          <IonButton
            size="small"
            fill="outline"
            data-testid="approval-retry"
            @click="refresh()"
          >
            {{ t('base.approval.retry') }}
          </IonButton>
        </template>
      </InlineFeedback>
      <template v-else-if="people.length > 0">
        <PinDoor
          :people="people"
          :pin-length="pinLength"
          :choose-label="t('base.approval.who')"
          :back-label="t('base.approval.another')"
          :error="error"
          :busy="busy"
          @enter="send"
          @choose="error = ''"
        />
      </template>
      <template v-else>
        <p
          class="approval-dialog__nobody"
          data-testid="approval-nobody"
        >
          {{ t('base.approval.nobody') }}
        </p>
        <p
          v-if="error"
          class="approval-dialog__error"
          role="alert"
        >
          {{ error }}
        </p>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* What scrolls when the screen is too short for the whole pad (a phone on its side): the content, under the title. */
.approval-dialog__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.approval-dialog {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  max-width: 28rem;
  margin: 0 auto;
}

.approval-dialog__action {
  margin: 0;
  align-self: stretch;
  font-weight: 600;
}

.approval-dialog__hint,
.approval-dialog__nobody {
  margin: 0;
  align-self: stretch;
  color: var(--ion-color-medium);
  font-size: 0.875rem;
}

.approval-dialog__error {
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>

<style>
/* Not scoped: Ionic moves the dialog to ion-app, and every rule hangs from its own class (APPROVAL_DIALOG_CLASS of
   lib/approval.ts). From a tablet up it is as tall as its content, the whole PIN pad with the 0 and erase in view, as
   Square's and Toast's manager override, never Ionic's fixed 600×600 card, which cut that row; a screen too short for
   it scrolls the content under the title. A phone keeps the full-screen dialog. */
@media only screen and (min-width: 768px) and (min-height: 600px) {
  ion-modal.approval-dialog-modal {
    --height: auto;
  }

  ion-modal.approval-dialog-modal .ion-page {
    max-height: calc(100vh - 32px);
    max-height: calc(100dvh - 32px);
  }
}
</style>
