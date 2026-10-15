<script setup lang="ts">
// «Pay this line with a voucher» (SALE-F27, SERVICE-F22; the old `erp-services-voucher-tender`): the
// customer's vouchers that cover the line's service (Services' `service.grant.tender_options`, live, so
// another till spending a session shows here), each a card with its name, «<n> sessions left · <m> after
// this one» (or «Unlimited sessions») and «Expires on <day>». The one spent first comes chosen, with
// why; «<n> valid vouchers» when there are more; a tap chooses another. «Spend one session» pays the line
// with it (`sale.order.apply_voucher`, which holds the session): the sheet's preview then shows the line
// paid. A read that fails never reads «no vouchers»: it says so with «Retry». Mounted per line, while the
// line is not paid and the check has a customer.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSkeletonText } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import type { TenderOptionOut } from '../../../../service/frontend/operations';
import { useLocale, useT } from '../../composables/useT';
import { formatDay } from '../../lib/format';
import { refusal } from '../../lib/refusal';

const props = defineProps<{ orderId: string; lineId: string; serviceId: string; customerId: string }>();

const t = useT();
const locale = useLocale();

/** The reasons the first option can give; anything else reads the generic sentence. */
const REASONS = ['only_option', 'finite_before_unlimited', 'expires_first', 'already_started', 'fewest_sessions_left', 'oldest_voucher', 'stable_order'];

const options = useLive('service.grant.tender_options', () => ({ customer_id: props.customerId, service_id: props.serviceId, limit: 20, offset: 0 }));
const apply = useCommand('sale.order.apply_voucher');

const rows = computed<TenderOptionOut[]>(() => options.data.value?.rows ?? []);
const picked = shallowRef<string | null>(null);
const chosen = computed(() => {
  const ids = rows.value.map((row) => row.grant_id);
  if (picked.value && ids.includes(picked.value)) return picked.value;
  return rows.value.find((row) => row.is_default)?.grant_id ?? ids[0] ?? null;
});
const candidates = computed(() => rows.value[0]?.candidate_count ?? rows.value.length);
const failure = shallowRef('');

function counter(row: TenderOptionOut): string {
  if (row.is_unlimited || row.remaining_after === null) return t('sale.voucher.unlimited');
  return t('sale.voucher.remainingAfter', { before: row.remaining_before, after: row.remaining_after });
}

function reason(row: TenderOptionOut): string {
  return REASONS.includes(row.default_reason) ? t(`sale.voucher.reason.${row.default_reason}`) : t('sale.voucher.reason.generic');
}

async function spend(): Promise<void> {
  const grant = chosen.value;
  if (!grant || apply.pending.value) return;
  failure.value = '';
  try {
    await apply.run({ order_id: props.orderId, line_id: props.lineId, grant_id: grant });
  } catch (error) {
    failure.value = refusal(error, t('sale.voucher.holdFailed'))?.message ?? t('sale.voucher.holdFailed');
  }
}
</script>

<template>
  <div class="voucher-slot">
    <div
      v-if="options.data.value === undefined && !options.error.value"
      :data-testid="`voucher-${lineId}-loading`"
    >
      <ion-skeleton-text
        animated
        class="voucher-slot__skeleton"
      />
    </div>
    <template v-else-if="options.error.value && !options.data.value">
      <InlineFeedback
        tone="danger"
        :data-testid="`voucher-${lineId}-load-error`"
      >
        {{ $t('sale.voucher.loadFailed') }}
        <template #actions>
          <ion-button
            fill="clear"
            size="small"
            :data-testid="`voucher-${lineId}-retry`"
            @click="options.refresh()"
          >
            {{ $t('sale.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
    </template>
    <InlineFeedback
      v-else-if="!rows.length"
      tone="neutral"
      :data-testid="`voucher-${lineId}-none`"
    >
      {{ $t('sale.voucher.none') }}
    </InlineFeedback>
    <template v-else>
      <div class="voucher-slot__head">
        <h4
          class="voucher-slot__title"
          :data-testid="`voucher-${lineId}-title`"
        >
          {{ $t('sale.voucher.title') }}
        </h4>
        <span
          v-if="candidates > 1"
          class="voucher-slot__candidates"
          :data-testid="`voucher-${lineId}-candidates`"
        >{{ $t('sale.voucher.candidates', { count: candidates }) }}</span>
      </div>
      <div
        role="radiogroup"
        class="voucher-slot__options"
        :aria-label="$t('sale.voucher.title')"
      >
        <button
          v-for="row in rows"
          :key="row.grant_id"
          type="button"
          role="radio"
          class="voucher-slot__option"
          :aria-checked="row.grant_id === chosen ? 'true' : 'false'"
          :data-testid="`voucher-${lineId}-option-${row.grant_id}`"
          @click="picked = row.grant_id"
        >
          <HubIcon
            v-if="row.grant_id === chosen"
            class="voucher-slot__radio"
            name="ion:checkmark-circle"
            aria-hidden="true"
          />
          <span
            v-else
            class="voucher-slot__ring"
            aria-hidden="true"
          />
          <span class="voucher-slot__body">
            <span class="voucher-slot__name">{{ row.package_name }}</span>
            <span class="voucher-slot__meta">
              <span class="voucher-slot__counter">{{ counter(row) }}</span>
              <span v-if="row.expires_at">{{ $t('sale.voucher.expires', { date: formatDay(row.expires_at, locale) }) }}</span>
            </span>
            <span
              v-if="row.is_default"
              class="voucher-slot__reason"
            >{{ reason(row) }}</span>
          </span>
        </button>
      </div>
      <InlineFeedback
        v-if="failure"
        tone="danger"
        :data-testid="`voucher-${lineId}-error`"
      >
        {{ failure }}
      </InlineFeedback>
      <div class="voucher-slot__actions">
        <ion-button
          :data-testid="`voucher-${lineId}-confirm`"
          :disabled="!chosen || apply.pending.value"
          @click="spend"
        >
          {{ apply.pending.value ? $t('sale.voucher.holding') : $t('sale.voucher.confirm') }}
        </ion-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.voucher-slot {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.voucher-slot__skeleton {
  height: 3.5rem;
  border-radius: 0.6rem;
}
.voucher-slot__head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem;
}
.voucher-slot__title {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
}
.voucher-slot__candidates,
.voucher-slot__meta,
.voucher-slot__reason {
  font-size: 0.8rem;
  color: var(--ion-color-medium, #6b6b6b);
}
.voucher-slot__options {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.voucher-slot__option {
  display: grid;
  grid-template-columns: auto 1fr;
  align-items: start;
  gap: 0.5rem;
  padding: 0.55rem 0.6rem;
  font: inherit;
  text-align: left;
  color: inherit;
  background: transparent;
  border: 1px solid var(--ion-border-color, #e2e0dc);
  border-radius: 0.6rem;
  cursor: pointer;
}
.voucher-slot__option[aria-checked='true'] {
  background: var(--ion-color-step-50, #f7f6f3);
  border-color: var(--ion-color-primary, #0091ce);
}
.voucher-slot__radio {
  margin-top: 0.1rem;
  font-size: 1.15rem;
  color: var(--ion-color-primary, #0091ce);
}
.voucher-slot__ring {
  width: 1.05rem;
  height: 1.05rem;
  margin: 0.1rem 0.05rem 0;
  border: 2px solid var(--ion-color-medium, #8b897f);
  border-radius: 50%;
}
.voucher-slot__body {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}
.voucher-slot__name {
  font-weight: 600;
}
.voucher-slot__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.voucher-slot__counter {
  font-variant-numeric: tabular-nums;
}
.voucher-slot__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}
.voucher-slot__actions ion-button {
  flex: 1 1 9rem;
}
@media (min-width: 40rem) {
  .voucher-slot__actions ion-button {
    flex: 0 0 auto;
  }
}
</style>
