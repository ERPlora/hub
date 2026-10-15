<script setup lang="ts">
// «Lines paid another way» (SALE-F27; the old sheet's section with Services' slot): each line of a service
// of this charge, by name, with its voucher slot. A line a voucher pays (the server's preview says so)
// reads «<voucher>: session spent. <n> left.» with «Undo» (`sale.order.remove_voucher`, which gives the
// session back). A voucher pays a line of ONE unit: a line of several whole units (2 to 50) is split
// first — «Split into N lines» (`sale.order.split_line`), the new lines go up (`split`) so a part charge
// takes them too —; one that cannot be split says no voucher can cover it. The rest offer the customer's
// vouchers (VoucherChooser). Without a customer only the lines a voucher already pays are listed.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
import { refusal } from '../../lib/refusal';
import type { PreviewLineOut } from '../../operations';
import VoucherChooser from './VoucherChooser.vue';

/** As the server's `MAX_LINE_SPLIT`: the most units one split writes. */
const MAX_SPLIT = 50;

const props = defineProps<{ orderId: string; lines: readonly PreviewLineOut[]; customerId: string | null }>();
const emit = defineEmits<{ split: [lineIds: string[]] }>();

const t = useT();
const remove = useCommand('sale.order.remove_voucher');
const split = useCommand('sale.order.split_line');

/** The line whose write is in flight, and the last refusal of each line. */
const busy = shallowRef<string | null>(null);
const failures = shallowRef<Record<string, string>>({});

interface Row {
  line: PreviewLineOut;
  id: string;
  units: number;
}

const rows = computed<Row[]>(() =>
  props.lines
    .filter((line) => line.order_line_id && line.service_id && !line.is_gift)
    .filter((line) => line.paid_by_voucher || (!!props.customerId && line.line_total > 0))
    .map((line) => ({ line, id: line.order_line_id as string, units: Number(line.quantity) })),
);

const splittable = (row: Row) => Number.isInteger(row.units) && row.units >= 2 && row.units <= MAX_SPLIT;

function held(line: PreviewLineOut): string {
  return line.voucher_remaining === null
    ? t('sale.voucher.heldUnlimited', { name: line.voucher_name })
    : t('sale.voucher.held', { name: line.voucher_name, after: line.voucher_remaining });
}

async function attempt(row: Row, write: () => Promise<void>, fallbackKey: string): Promise<void> {
  if (busy.value) return;
  busy.value = row.id;
  failures.value = { ...failures.value, [row.id]: '' };
  try {
    await write();
  } catch (error) {
    failures.value = { ...failures.value, [row.id]: refusal(error, t(fallbackKey))?.message ?? t(fallbackKey) };
  } finally {
    busy.value = null;
  }
}

const undo = (row: Row) =>
  attempt(row, async () => void (await remove.run({ order_id: props.orderId, line_id: row.id })), 'sale.voucher.releaseFailed');

const splitLine = (row: Row) =>
  attempt(
    row,
    async () => {
      const done = await split.run({ order_id: props.orderId, line_id: row.id });
      emit('split', [...(done.new_line_ids ?? [])]);
    },
    'sale.voucher.splitFailed',
  );
</script>

<template>
  <section
    v-if="rows.length"
    class="voucher-lines"
    data-testid="voucher-lines"
  >
    <h3
      class="voucher-lines__title"
      data-testid="voucher-lines-title"
    >
      {{ $t('sale.voucher.section') }}
    </h3>
    <div
      v-for="row in rows"
      :key="row.id"
      class="voucher-lines__line"
      :data-testid="`voucher-line-${row.id}`"
    >
      <p
        class="voucher-lines__name"
        :data-testid="`voucher-line-${row.id}-name`"
      >
        {{ row.line.name }}
      </p>
      <template v-if="row.line.paid_by_voucher">
        <InlineFeedback
          tone="success"
          :data-testid="`voucher-${row.id}-held`"
        >
          {{ held(row.line) }}
        </InlineFeedback>
        <div class="voucher-lines__actions">
          <ion-button
            fill="clear"
            :data-testid="`voucher-${row.id}-undo`"
            :disabled="busy === row.id"
            @click="undo(row)"
          >
            {{ $t('sale.voucher.undo') }}
          </ion-button>
        </div>
      </template>
      <template v-else-if="row.units !== 1">
        <template v-if="splittable(row)">
          <p
            class="voucher-lines__hint"
            :data-testid="`voucher-${row.id}-split-reason`"
          >
            {{ $t('sale.voucher.splitReason') }}
          </p>
          <div class="voucher-lines__actions">
            <ion-button
              fill="outline"
              :data-testid="`voucher-${row.id}-split`"
              :disabled="busy === row.id"
              @click="splitLine(row)"
            >
              {{ $t('sale.voucher.split', { n: row.units }) }}
            </ion-button>
          </div>
        </template>
        <p
          v-else
          class="voucher-lines__hint"
          :data-testid="`voucher-${row.id}-not-splittable`"
        >
          {{ $t('sale.voucher.notSplittable') }}
        </p>
      </template>
      <VoucherChooser
        v-else-if="customerId"
        :order-id="orderId"
        :line-id="row.id"
        :service-id="row.line.service_id as string"
        :customer-id="customerId"
      />
      <InlineFeedback
        v-if="failures[row.id]"
        tone="danger"
        :data-testid="`voucher-${row.id}-error`"
      >
        {{ failures[row.id] }}
      </InlineFeedback>
    </div>
  </section>
</template>

<style scoped>
.voucher-lines {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.voucher-lines__title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 700;
}
.voucher-lines__line {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  padding: 0.6rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: var(--ep-radius-sm, 10px);
}
.voucher-lines__name {
  margin: 0;
  font-weight: 600;
}
.voucher-lines__hint {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #6b6b6b);
}
.voucher-lines__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
</style>
