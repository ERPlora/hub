<script setup lang="ts">
// The body of the Refund window (SALE-F31; the old `erp-sale-refund`). What can go back is the server's
// (`sale.refund.options`, live): each tender's figures and each line's units. The window only PROPOSES:
// a full refund split by tender to begin with, the marked lines' share when lines are marked, the full
// one again with «Refund everything»; every amount can be edited. «Refund <amount>» says why it cannot
// go yet (aria-disabled: the tap answers, never dies). `sale.sale.refund` carries the attempt key born
// when the window opened and kept on a retry, so a lost answer never refunds twice; a refusal is read
// inside the window, which stays open. `sale.sale.refund` decides it all again. A line a voucher paid
// (SALE-F32) gives its session back when it is marked, also with no money at all: a sale paid whole with a
// voucher (0,00 €) opens with its sessions to mark.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonSpinner, IonTextarea } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney } from '../../lib/format';
import { refusal } from '../../lib/refusal';
import type { RefundOptionsOut, TenderOption } from '../../operations';
import {
  allocations,
  amountInput,
  attemptKey,
  parseAmount,
  type Picked,
  proposal,
  refundableTotal,
  refundBlock,
  refundLines,
  sessionsLeft,
  sessionsPicked,
} from './refund';
import RefundLines from './RefundLines.vue';
import RefundTenderCard from './RefundTenderCard.vue';

const props = defineProps<{ saleId: string }>();
const emit = defineEmits<{ refunded: [] }>();

const t = useT();
const locale = useLocale();
const money = (cents: number): string => formatMoney(cents, locale.value);

const { data, error: loadError, refresh } = useLive('sale.refund.options', () => ({ sale_id: props.saleId }));
const command = useCommand('sale.sale.refund');

/** This attempt's key: born with the window, the same on every retry. */
const key = attemptKey(props.saleId);

/** What the person typed per tender, the method chosen where one is needed, the units marked, the reason. */
const typed = ref<Record<string, string>>({});
const destinations = ref<Record<string, string>>({});
const picked = shallowRef<Picked>({});
const reason = shallowRef('');
/** Why the last refund did not go through. */
const failure = shallowRef('');

const tenders = computed<TenderOption[]>(() => [...(data.value?.tenders ?? [])].sort((a, b) => a.position - b.position));
const nothingLeft = computed(
  () => !!data.value && (data.value.status !== 'completed' || (refundableTotal(tenders.value) <= 0 && sessionsLeft(data.value.lines) === 0)),
);
/** The voucher sessions marked to go back (SALE-F32). */
const sessions = computed(() => (data.value ? sessionsPicked(data.value.lines, picked.value) : 0));

function propose(options: RefundOptionsOut, marked: Picked): void {
  const split = proposal(options.tenders, options.lines, marked);
  typed.value = Object.fromEntries(Object.entries(split).map(([id, cents]) => [id, amountInput(cents, locale.value)]));
}

// The first answer seeds the proposal; a later one (another refund elsewhere) keeps what was typed.
const stopSeeding = watch(
  data,
  (now) => {
    if (!now) return;
    propose(now, picked.value);
    stopSeeding();
  },
  { immediate: true, flush: 'sync' },
);

function setPicked(next: Picked): void {
  picked.value = next;
  if (data.value) propose(data.value, next);
}

function proposeAll(): void {
  if (data.value) propose(data.value, {});
}

const amounts = computed(() => Object.fromEntries(tenders.value.map((tender) => [tender.payment_id, parseAmount(typed.value[tender.payment_id] ?? '')])));
const total = computed(() => Object.values(amounts.value).reduce((sum, cents) => (Number.isFinite(cents) ? sum + cents : sum), 0));
const block = computed(() => refundBlock(tenders.value, amounts.value, destinations.value, reason.value, sessions.value));

const blockText = computed(() => {
  const now = block.value;
  if (!now) return '';
  if (now.kind === 'nothing') return refundableTotal(tenders.value) > 0 ? t('sale.refund.nothingToReturn') : t('sale.refund.markSession');
  if (now.kind === 'reason') return t('sale.refund.reasonRequired');
  if (now.kind === 'invalid') return t('sale.refund.amountInvalid', { method: now.tender.method_name });
  if (now.kind === 'overCap') return t('sale.refund.overCap', { method: now.tender.method_name, amount: money(now.amount), remaining: money(now.tender.remaining) });
  return t('sale.refund.needsDestination', { method: now.tender.method_name });
});

/** The message under a tender's amount: what is wrong with that very amount. */
function cardError(tender: TenderOption): string | undefined {
  const now = block.value;
  if ((now?.kind === 'invalid' || now?.kind === 'overCap') && now.tender.payment_id === tender.payment_id) return blockText.value;
  return undefined;
}

async function confirm(): Promise<void> {
  if (command.pending.value || !data.value || nothingLeft.value) return;
  if (blockText.value) {
    void toastError(blockText.value);
    return;
  }
  const lines = refundLines(data.value.lines, picked.value);
  failure.value = '';
  try {
    await command.run({
      sale_id: props.saleId,
      reason: reason.value.trim(),
      idempotency_key: key,
      allocations: allocations(tenders.value, amounts.value, destinations.value),
      ...(lines.length ? { lines } : {}),
    });
  } catch (err) {
    // Unworded (no network, a proxy's page): it may have gone through; the same key never repeats it.
    failure.value = refusal(err, t('sale.refund.unknown'))?.message ?? t('sale.refund.unknown');
    return;
  }
  void toastSuccess(t('sale.refund.done'));
  emit('refunded');
}

defineExpose({ confirm });
</script>

<template>
  <div class="sale-refund">
    <InlineFeedback
      v-if="loadError && !data"
      tone="danger"
      data-testid="refund-load-error"
    >
      {{ $t('sale.refund.loadError') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="refund-retry"
          @click="refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <div
      v-else-if="!data"
      class="sale-refund__loading"
      data-testid="refund-loading"
      role="status"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      <span>{{ $t('sale.refund.loading') }}</span>
    </div>
    <InlineFeedback
      v-else-if="nothingLeft"
      tone="warning"
      icon="information-circle-outline"
      data-testid="refund-nothing"
    >
      {{ $t('sale.refund.nothing') }}
    </InlineFeedback>
    <template v-else>
      <p
        class="sale-refund__hint"
        data-testid="refund-explain"
      >
        {{ $t('sale.refund.explain') }}
      </p>
      <RefundLines
        v-if="data.lines.length"
        :lines="data.lines"
        :picked="picked"
        @update:picked="setPicked"
      />
      <div class="sale-refund__tenders">
        <RefundTenderCard
          v-for="tender in tenders"
          :key="tender.payment_id"
          :amount="typed[tender.payment_id] ?? ''"
          :destination="destinations[tender.payment_id] ?? ''"
          :tender="tender"
          :error="cardError(tender)"
          @update:amount="typed[tender.payment_id] = $event"
          @update:destination="destinations[tender.payment_id] = $event"
        />
      </div>
      <ion-button
        v-if="tenders.length"
        class="sale-refund__propose"
        size="small"
        fill="clear"
        data-testid="refund-propose-all"
        @click="proposeAll"
      >
        {{ $t('sale.refund.proposeAll') }}
      </ion-button>
      <ion-textarea
        data-testid="refund-reason"
        :label="$t('sale.refund.reason')"
        :placeholder="$t('sale.refund.reasonPlaceholder')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="500"
        :auto-grow="true"
        :value="reason"
        @ion-input="reason = String($event.detail.value ?? '')"
      />
      <div
        class="sale-refund__total"
        data-testid="refund-total"
      >
        <span>{{ $t('sale.refund.total') }}</span>
        <span class="sale-refund__total-value">{{ money(total) }}</span>
      </div>
      <p
        v-if="blockText"
        class="sale-refund__blocked"
        data-testid="refund-blocked"
      >
        {{ blockText }}
      </p>
      <InlineFeedback
        v-if="failure"
        tone="danger"
        data-testid="refund-error"
      >
        {{ failure }}
      </InlineFeedback>
      <ion-button
        class="sale-refund__confirm"
        data-testid="refund-confirm"
        expand="block"
        color="danger"
        :disabled="command.pending.value"
        :aria-disabled="blockText ? 'true' : undefined"
        :data-blocked="blockText ? 'true' : undefined"
        @click="confirm"
      >
        <ion-spinner
          v-if="command.pending.value"
          slot="start"
          name="crescent"
          aria-hidden="true"
        />
        {{ total > 0 || !sessions ? $t('sale.refund.confirm', { amount: money(total) }) : $t('sale.refund.confirmSession') }}
      </ion-button>
    </template>
  </div>
</template>

<style scoped>
.sale-refund {
  display: grid;
  gap: 0.85rem;
  max-width: 46rem;
}
.sale-refund__loading {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  padding: 1.5rem 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.sale-refund__hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.9rem;
}
.sale-refund__tenders {
  display: grid;
  gap: 0.6rem;
}
.sale-refund__propose {
  justify-self: start;
  margin: 0;
}
.sale-refund__total {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-weight: 600;
}
.sale-refund__total-value {
  font-size: 1.2rem;
  font-variant-numeric: tabular-nums;
}
.sale-refund__blocked {
  margin: 0;
  color: var(--ion-color-danger, #c5000f);
  font-size: 0.9rem;
}
/* Blocked, it still takes the tap (aria-disabled): it only looks quieter. */
.sale-refund__confirm[data-blocked='true'] {
  opacity: 0.55;
}
.sale-refund__confirm {
  margin: 0;
}
</style>
