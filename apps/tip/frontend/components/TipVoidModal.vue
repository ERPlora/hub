<script setup lang="ts">
// «Void» a tip (TIP-F06): «Void the tip of <sale>», what voiding does, «Reason» and «Void» / «Cancel». It runs
// `tip.tip.void` with the reason as typed; the server asks for one under its field when it is missing, and any other
// refusal is read inside the window, which stays open. Voided, the row turns «Voided» by itself (live).
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../../../sale/frontend/composables/useT';
import { refusal } from '../../../sale/frontend/lib/refusal';
import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';
import type { TipOut } from '../operations';

const props = defineProps<{ tip: Pick<TipOut, 'id' | 'sale_number' | 'pool'> | null }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const command = useCommand('tip.tip.void');
const reason = shallowRef('');

watch(
  open,
  (now) => {
    if (!now) return;
    reason.value = '';
    command.error.value = null;
  },
  { immediate: true },
);

const title = computed(() =>
  props.tip?.pool ? t('tip.void.poolTitle') : t('tip.void.title', { sale: props.tip?.sale_number ?? '' }),
);
const error = computed(() => refusal(command.error.value, t('tip.void.failed')));

async function confirm(): Promise<void> {
  const tip = props.tip;
  if (!tip) return;
  try {
    await command.run({ id: tip.id, reason: reason.value });
  } catch {
    return; // The window shows `command.error`.
  }
  toastSuccess(t('tip.void.done'));
  open.value = false;
}

const canDismiss = useUnsavedFormOnOpen('tip-void', () => reason.value, open);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    size="sm"
    testid="tip-void"
    role="alertdialog"
    submit-color="danger"
    :title="title"
    :submit-label="$t('tip.void.confirm')"
    :cancel-label="$t('tip.void.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="confirm"
  >
    <template #default="{ fieldErrors }">
      <p data-testid="tip-void-explain">
        {{ $t('tip.void.explain') }}
      </p>
      <ion-textarea
        data-testid="tip-void-reason"
        name="reason"
        :label="$t('tip.void.reason')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="255"
        :auto-grow="true"
        :value="reason"
        :error-text="fieldErrors.reason"
        :class="{ 'ion-invalid': !!fieldErrors.reason, 'ion-touched': !!fieldErrors.reason }"
        @ion-input="reason = String($event.detail.value ?? '')"
      />
    </template>
  </FormModal>
</template>
