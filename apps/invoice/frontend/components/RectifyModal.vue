<script setup lang="ts">
// «Rectify» an invoice (INVOICE-F08; the old «Devolución» dialog, renamed: no money moves here): «Rectify
// <number>», the note of what will happen, the «Type of rectifying invoice» (R1 by default, R2–R4 to choose;
// a ticket is always R5 and says so), «Reason» (required) and «Issue rectifying invoice». Without a reason it
// says so and sends nothing; with one it runs `invoice.invoice.rectify` (no date: the server dates it today)
// and shows the result in the same window with «Close». A rectifying or cancelled invoice only says why. A
// refusal is read inside the window, in the server's words.
import { FormModal, type FormModalError, InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../composables/useT';
import { isSimplified } from '../lib/invoice';
import { refusal } from '../lib/refusal';
import type { InvoiceOut, InvoiceRowOut, RectificationType } from '../operations';

const props = defineProps<{ invoice: Pick<InvoiceRowOut, 'id' | 'number' | 'invoice_type' | 'status'> | null }>();

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ rectified: [rectification: InvoiceOut] }>();

const TYPES: readonly RectificationType[] = ['R1', 'R2', 'R3', 'R4'];

const t = useT();
const command = useCommand('invoice.invoice.rectify');
const reason = shallowRef('');
const type = shallowRef<RectificationType>('R1');
/** The window's own refusal (no reason), before anything is sent. */
const missing = shallowRef(false);
/** The rectifying invoice issued: the window shows the result until it is closed. */
const done = shallowRef<InvoiceOut | null>(null);

watch(
  open,
  (now) => {
    if (!now) return;
    reason.value = '';
    type.value = 'R1';
    missing.value = false;
    done.value = null;
    command.error.value = null;
  },
  { immediate: true },
);

const simplified = computed(() => isSimplified(props.invoice?.invoice_type ?? ''));
/** Why this document cannot be rectified at all, if so. */
const blocked = computed(() => {
  if (!props.invoice) return '';
  if (props.invoice.invoice_type.startsWith('R')) return t('invoice.rectify.isRectifying');
  if (props.invoice.status === 'cancelled') return t('invoice.rectify.cancelled');
  return '';
});
const error = computed<FormModalError | null>(() =>
  missing.value ? { message: t('invoice.rectify.reasonRequired') } : refusal(command.error.value, t('invoice.rectify.failed')),
);
const result = computed(() => {
  const rect = done.value;
  if (!rect) return '';
  const original = rect.rectifies;
  return original?.status === 'cancelled'
    ? t('invoice.rectify.done', { rectification: rect.number, number: original.number })
    : t('invoice.rectify.doneLeft', { rectification: rect.number });
});

async function issue(): Promise<void> {
  const invoice = props.invoice;
  if (!invoice || blocked.value || done.value || command.pending.value) return;
  const text = reason.value.trim();
  missing.value = !text;
  if (!text) return;
  let answer;
  try {
    answer = await command.run({
      invoice_id: invoice.id,
      reason: text,
      ...(simplified.value ? {} : { rectification_type: type.value }),
    });
  } catch {
    return; // The window shows `command.error`.
  }
  if (answer.invoice) {
    done.value = answer.invoice;
    emit('rectified', answer.invoice);
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="invoice-rectify"
    role="alertdialog"
    submit-color="danger"
    :title="$t('invoice.rectify.title', { number: invoice?.number ?? '' })"
    :submit-label="$t('invoice.rectify.submit')"
    :cancel-label="$t('invoice.cancel')"
    :pending="command.pending.value"
    :error="done || blocked ? null : error"
    @submit="issue"
  >
    <InlineFeedback
      v-if="done"
      tone="success"
      data-testid="invoice-rectify-done"
    >
      {{ result }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="blocked"
      tone="warning"
      data-testid="invoice-rectify-blocked"
    >
      {{ blocked }}
    </InlineFeedback>
    <div
      v-else
      class="invoice-rectify__fields"
    >
      <p
        class="invoice-rectify__note"
        data-testid="invoice-rectify-note"
      >
        {{ $t('invoice.rectify.note') }}
      </p>
      <p
        v-if="simplified"
        class="invoice-rectify__note"
        data-testid="invoice-rectify-simplified"
      >
        {{ $t('invoice.rectify.simplified') }}
      </p>
      <ion-select
        v-else
        data-testid="invoice-rectify-type"
        :label="$t('invoice.rectify.type')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="type"
        @ion-change="type = $event.detail.value as RectificationType"
      >
        <ion-select-option
          v-for="code in TYPES"
          :key="code"
          :value="code"
        >
          {{ $t(`invoice.rectify.types.${code}`) }}
        </ion-select-option>
      </ion-select>
      <ion-textarea
        data-testid="invoice-rectify-reason"
        :label="$t('invoice.rectify.reason')"
        :placeholder="$t('invoice.rectify.reasonPlaceholder')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="500"
        :auto-grow="true"
        :value="reason"
        @ion-input="reason = String($event.detail.value ?? '')"
      />
    </div>
    <template
      v-if="done || blocked"
      #footer
    >
      <ion-button
        data-testid="invoice-rectify-close-result"
        @click="open = false"
      >
        {{ $t('invoice.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.invoice-rectify__fields {
  display: grid;
  gap: 14px;
}
.invoice-rectify__note {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.9rem;
}
</style>
