<script setup lang="ts">
// The steps of a reservation that ask first (RESERVATION-F09, F10, F20; the market: a confirmation naming
// whose booking and when). «Cancel reservation» keeps an optional reason; «Mark no-show» and «Delete for
// good» only ask. Each runs its own operation; a refusal stays in the dialog, and once done it closes and
// emits `done` with its kind.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatDay, formatTime } from '../lib/clock';
import type { ReservationOut } from '../operations';

export type StepKind = 'cancel' | 'no_show' | 'delete';

const props = defineProps<{ kind: StepKind; reservation: ReservationOut | null }>();
const emit = defineEmits<{ done: [kind: StepKind] }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const cancel = useCommand('reservation.reservation.cancel');
const noShow = useCommand('reservation.reservation.no_show');
const remove = useCommand('reservation.reservation.delete');
const command = computed(() => ({ cancel, no_show: noShow, delete: remove })[props.kind]);
const reason = ref('');

const KEYS: Record<StepKind, string> = { cancel: 'cancel', no_show: 'noShow', delete: 'delete' };
const key = computed(() => KEYS[props.kind]);

watch(open, (isOpen) => {
  if (!isOpen) return;
  reason.value = '';
  command.value.error.value = null;
});

const message = computed(() => {
  const item = props.reservation;
  if (!item) return '';
  const guest = item.guest_name || t('reservation.erasedCustomer');
  const when = `${formatDay(item.date, locale.value)} · ${formatTime(item.time, locale.value)}`;
  return t(`reservation.${key.value}.message`, { guest, when });
});

async function confirm(): Promise<void> {
  const item = props.reservation;
  if (!item) return;
  try {
    if (props.kind === 'cancel') await cancel.run({ id: item.id, reason: reason.value.trim() });
    else if (props.kind === 'no_show') await noShow.run({ id: item.id });
    else await remove.run({ id: item.id });
  } catch {
    return; // The dialog says why.
  }
  open.value = false;
  emit('done', props.kind);
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :testid="`reservation-step-${kind}`"
    size="sm"
    role="alertdialog"
    :title="t(`reservation.${key}.title`)"
    :submit-label="t(`reservation.${key}.confirm`)"
    :cancel-label="kind === 'cancel' ? $t('reservation.cancel.keep') : $t('reservation.cancelButton')"
    submit-color="danger"
    :pending="command.pending.value"
    :error="command.error.value"
    @submit="confirm"
  >
    <p>{{ message }}</p>
    <ion-textarea
      v-if="kind === 'cancel'"
      :data-testid="`reservation-step-${kind}-reason`"
      :value="reason"
      :label="$t('reservation.cancel.reason')"
      label-placement="floating"
      fill="outline"
      mode="md"
      :maxlength="500"
      @ion-input="reason = String($event.detail.value ?? '')"
    />
  </FormModal>
</template>
