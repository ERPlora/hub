<script setup lang="ts">
// The body of «Close session · S-…» (CASH_REGISTER-F07, F08, F09; the old dashboard's close panel). It only
// exists while the window is open, so it only reads then: the session (its expected cash, which the server
// leaves empty when a blind count hides it from this person), its counts (the counted cash starts from the
// last CLOSING count — counting the same drawer twice is how a fake difference is made; never an opening
// one) and, for the shift review, Sales' open checks, the kitchen tickets not served yet (Kitchen's
// `kitchen.ticket.board`, KITCHEN-F31) and the prints that did not come out (Printing's queue). An app that
// is off in this hub has nothing pending; a reading refused makes the review incomplete. The expected and
// the difference follow what is typed. The counted cash is always asked for. With something pending the
// first press warns, the second closes («Close anyway»): it warns, it never prevents. Success says the
// three figures and tells the window.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { moneyDecimals, formatMoney, formatSignedMoney, moneyFieldText, moneyRefusal, readMoney, useBusinessMoney } from '../lib/money';
import { refusal } from '../lib/refusal';
import MoneyField from './MoneyField.vue';
import ShiftReview from './ShiftReview.vue';

const props = defineProps<{ session: { id: string; number: string } }>();
const emit = defineEmits<{ closed: []; cancel: [] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const detail = useLive('cash_register.session.get', () => ({ session_id: props.session.id }));
const counts = useLive('cash_register.count.list', () => ({ session_id: props.session.id, limit: 20 }));
const checks = useLive('sale.order.list', { status: 'open', limit: 20 });
const kitchen = useLive('kitchen.ticket.board', {});
const prints = useLive('printing.job.summary', {});
const command = useCommand('cash_register.session.close');

const counted = shallowRef('');
const notes = shallowRef('');
const touched = shallowRef(false);
const countedRefusal = shallowRef<string | null>(null);
const acknowledged = shallowRef(false);

// The last closing count seeds the field once, while the person has not typed anything.
watch(
  () => counts.data.value?.rows,
  (rows) => {
    const last = rows?.find((count) => count.type === 'closing');
    if (last && !touched.value) counted.value = moneyFieldText(last.total, locale.value, moneyDecimals(business.value));
  },
  { immediate: true },
);

function type(value: string): void {
  touched.value = true;
  counted.value = value;
}

const expected = computed(() => detail.data.value?.summary.expected_cash ?? null);
const read = computed(() => readMoney(counted.value, moneyDecimals(business.value), business.value?.currency));
const difference = computed(() => (expected.value !== null && read.value.ok && read.value.cents !== null ? read.value.cents - expected.value : null));

/** A reading of the review: answered, refused (the review is incomplete), off in this hub (nothing pending)
 *  or still on its way. */
function reading<T>(live: { data: { value: T | undefined }; error: { value: { code: string } | null } }) {
  const error = live.error.value;
  const off = error?.code === 'app_inactive';
  return { answer: off ? undefined : live.data.value, failed: !!error && !off, waiting: !error && live.data.value === undefined };
}

const review = computed(() => {
  const open = reading(checks);
  const board = reading(kitchen);
  const queue = reading(prints);
  const tickets = [...(board.answer?.cooking ?? []), ...(board.answer?.ready ?? [])];
  const stuck = (queue.answer?.usages ?? []).filter((row) => row.pending + row.failed > 0);
  return {
    checking: open.waiting || board.waiting || queue.waiting,
    incomplete: open.failed || board.failed || queue.failed,
    openChecks: open.answer?.total ?? 0,
    labels: (open.answer?.rows ?? []).map((order) => order.label).filter((label) => !!label),
    unserved: (board.answer?.cooking_count ?? 0) + (board.answer?.ready_count ?? 0),
    unservedLabels: tickets.map((ticket) => ticket.label || `#${ticket.short_number}`),
    prints: stuck.reduce((sum, row) => sum + row.pending + row.failed, 0),
    printUsages: stuck.map((row) => row.usage),
  };
});
/** Something is still open at the close: the first press only warns. */
const pending = computed(() => review.value.openChecks + review.value.unserved + review.value.prints > 0);

const error = computed(() => refusal(command.error.value, t('cash_register.close.failed')));
const countedError = computed(() => countedRefusal.value ?? error.value?.fields?.closing_balance ?? null);

async function confirm(): Promise<void> {
  const value = read.value;
  countedRefusal.value = value.ok ? (value.cents === null ? t('cash_register.close.countedRequired') : null) : moneyRefusal(value, t, locale.value, business.value);
  if (!value.ok || value.cents === null) return;
  if (pending.value && !acknowledged.value) {
    acknowledged.value = true;
    return;
  }
  let closed;
  try {
    closed = await command.run({ session_id: props.session.id, closing_balance: value.cents, closing_notes: notes.value.trim() });
  } catch {
    return; // The form shows `command.error`.
  }
  void toastSuccess(
    t('cash_register.close.done', {
      number: closed.number,
      expected: formatMoney(closed.expected_balance, locale.value, business.value),
      counted: formatMoney(closed.closing_balance, locale.value, business.value),
      difference: formatSignedMoney(closed.difference, locale.value, business.value),
    }),
  );
  emit('closed');
}

defineExpose({ confirm });
</script>

<template>
  <div class="cash-close">
    <ShiftReview
      v-bind="review"
      :acknowledged="acknowledged"
    />
    <dl
      v-if="expected !== null"
      class="cash-close__figures"
      data-testid="cash-register-close-expected"
    >
      <div>
        <dt>{{ $t('cash_register.close.expected') }}</dt>
        <dd>{{ formatMoney(expected, locale, business) }}</dd>
      </div>
      <div>
        <dt>{{ $t('cash_register.close.difference') }}</dt>
        <dd>{{ formatSignedMoney(difference, locale, business) }}</dd>
      </div>
    </dl>
    <MoneyField
      :model-value="counted"
      testid="cash-register-close-counted"
      :label="$t('cash_register.close.counted')"
      :error="countedError"
      @update:model-value="type"
    />
    <ion-input
      data-testid="cash-register-close-notes"
      :label="$t('cash_register.close.notes')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      :maxlength="1000"
      :value="notes"
      @ion-input="notes = String($event.detail.value ?? '')"
    />
    <InlineFeedback
      v-if="error"
      tone="danger"
      icon="alert-circle-outline"
      data-testid="cash-register-close-error"
    >
      {{ error.message }}
    </InlineFeedback>
    <div class="cash-close__actions">
      <ion-button
        fill="outline"
        data-testid="cash-register-close-cancel"
        :disabled="command.pending.value"
        @click="emit('cancel')"
      >
        {{ $t('cash_register.close.cancel') }}
      </ion-button>
      <ion-button
        color="danger"
        data-testid="cash-register-close-submit"
        :disabled="command.pending.value"
        @click="confirm"
      >
        <ion-spinner
          v-if="command.pending.value"
          slot="start"
          name="crescent"
        />
        {{ acknowledged ? $t('cash_register.close.anyway') : $t('cash_register.close.submit') }}
      </ion-button>
    </div>
  </div>
</template>

<style scoped>
.cash-close {
  display: grid;
  gap: 0.85rem;
}
.cash-close__figures {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem 1rem;
  margin: 0;
}
.cash-close__figures dt {
  font-size: 0.8rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.cash-close__figures dd {
  margin: 0;
  font-weight: 600;
}
.cash-close__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.cash-close__actions ion-button {
  min-height: 44px;
  margin: 0;
}
</style>
