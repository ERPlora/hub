<script setup lang="ts">
// «Void» a charged sale (SALE-F30; the old `erp-sale-void`): «Void sale <number>», the explanation,
// «Reason (required)» and «Void» / «Cancel». Without a reason it says so and sends nothing; with one it
// runs `sale.sale.void`, says «Sale voided» and closes (the row turns Voided and «Voided» goes up by
// themselves, live). A refusal (a full invoice, a sale with refunds, voided elsewhere at the same time)
// is read inside the window, in the server's words (a failure it did not word: «The sale could not be
// voided»), and the window stays open.
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../../composables/useT';
import { refusal } from '../../lib/refusal';
import type { SaleRow } from '../../operations';

const props = defineProps<{ sale: Pick<SaleRow, 'id' | 'number'> | null }>();

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ voided: [] }>();

const t = useT();
const command = useCommand('sale.sale.void');
const reason = shallowRef('');
/** The window's own refusal (no reason), before anything is sent. */
const missing = shallowRef(false);

watch(
  open,
  (now) => {
    if (!now) return;
    reason.value = '';
    missing.value = false;
    command.error.value = null;
  },
  { immediate: true },
);

const error = computed<FormModalError | null>(() =>
  missing.value ? { message: t('sale.void.reasonRequired') } : refusal(command.error.value, t('sale.void.failed')),
);

async function confirm(): Promise<void> {
  const sale = props.sale;
  if (!sale) return;
  const text = reason.value.trim();
  missing.value = !text;
  if (!text) return;
  try {
    await command.run({ sale_id: sale.id, reason: text });
  } catch {
    return; // The window shows `command.error`.
  }
  void toastSuccess(t('sale.void.done'));
  open.value = false;
  emit('voided');
}
</script>

<template>
  <FormModal
    v-model:open="open"
    size="sm"
    testid="sale-void"
    role="alertdialog"
    submit-color="danger"
    :title="$t('sale.void.title', { number: sale?.number ?? '' })"
    :submit-label="$t('sale.void.confirm')"
    :cancel-label="$t('sale.void.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="confirm"
  >
    <p
      class="sale-void__explain"
      data-testid="sale-void-explain"
    >
      {{ $t('sale.void.explain') }}
    </p>
    <ion-textarea
      data-testid="sale-void-reason"
      :label="$t('sale.void.reason')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      :maxlength="500"
      :auto-grow="true"
      :value="reason"
      @ion-input="reason = String($event.detail.value ?? '')"
    />
  </FormModal>
</template>

<style scoped>
.sale-void__explain {
  margin: 0 0 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.9rem;
}
</style>
