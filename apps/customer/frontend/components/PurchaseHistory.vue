<script setup lang="ts">
// «Purchases» of a card (CUSTOMER-F23): each sale with its date, amount and status, newest first,
// 50 at a time, filterable by status; live (`customer.purchase.list` re-runs when a sale is paid,
// voided or refunded). A refund is a line of its own, its amount negative (F22). New on the card:
// the product only gave them through the assistant.
import { formatDateTime, StatusPill } from '@erplora/ui/components';
import { IonButton, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { formatMoney } from '../lib/money';
import { windowsOf } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { PurchaseRow } from '../operations';

const props = defineProps<{ customerId: string }>();

const STEP = 50;
const { t, locale } = useCustomerI18n();

type Status = PurchaseRow['status'];
const STATUSES: Status[] = ['confirmed', 'voided', 'refunded'];
/** How each status reads and its tone. */
const LOOK: Record<Status, { label: string; tone: 'success' | 'neutral' | 'warning' }> = {
  confirmed: { label: 'customer.purchases.confirmed', tone: 'success' },
  voided: { label: 'customer.purchases.voided', tone: 'neutral' },
  refunded: { label: 'customer.purchases.refunded', tone: 'warning' },
};

const status = ref<'all' | Status>('all');
const limit = ref(STEP);
// «Show more» grows what is shown by 50; the server is asked in windows of ≤ 100 (`useLiveList`).
const windows = computed(() => windowsOf(0, limit.value));
const live = useLiveList(
  'customer.purchase.list',
  () => ({ customer_id: props.customerId, ...(status.value === 'all' ? {} : { status: status.value }) }),
  windows,
);
const rows = computed(() => live.data.value?.rows ?? []);
const more = computed(() => (live.data.value ? live.data.value.total > live.data.value.rows.length : false));

function filterBy(event: CustomEvent<{ value?: unknown }>): void {
  const value = event.detail.value;
  status.value = STATUSES.includes(value as Status) ? (value as Status) : 'all';
  limit.value = STEP;
}
</script>

<template>
  <div
    class="customer-purchases"
    data-testid="customer-purchases"
  >
    <div class="customer-purchases__head">
      <h3>{{ $t('customer.purchases.heading') }}</h3>
      <ion-select
        data-testid="customer-purchases-filter"
        interface="popover"
        :aria-label="$t('customer.purchases.filter')"
        :value="status"
        @ion-change="filterBy"
      >
        <ion-select-option value="all">
          {{ $t('customer.common.all') }}
        </ion-select-option>
        <ion-select-option
          v-for="option in STATUSES"
          :key="option"
          :value="option"
        >
          {{ $t(LOOK[option].label) }}
        </ion-select-option>
      </ion-select>
    </div>
    <p
      v-if="live.status.value === 'error' && live.error.value?.code !== 'app_inactive'"
      class="customer-purchases__error"
      data-testid="customer-purchases-error"
      role="alert"
    >
      {{ $t('customer.purchases.loadError') }}: {{ live.error.value?.message }}
    </p>
    <ul
      v-if="rows.length"
      class="customer-purchases__list"
    >
      <li
        v-for="row in rows"
        :key="row.id"
        data-testid="customer-purchase"
        :data-status="row.status"
      >
        <span class="customer-purchases__date">{{ formatDateTime(row.recorded_at, locale) }}</span>
        <span class="customer-purchases__amount">{{ formatMoney(row.amount, locale) }}</span>
        <StatusPill
          size="sm"
          :tone="LOOK[row.status].tone"
          :label="t(LOOK[row.status].label)"
        />
      </li>
    </ul>
    <p
      v-else-if="live.data.value"
      class="customer-purchases__empty"
      data-testid="customer-purchases-empty"
    >
      {{ $t('customer.purchases.empty') }}
    </p>
    <ion-button
      v-if="more"
      size="small"
      fill="clear"
      data-testid="customer-purchases-more"
      @click="limit += STEP"
    >
      {{ $t('customer.purchases.more') }}
    </ion-button>
  </div>
</template>

<style scoped>
.customer-purchases__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.customer-purchases h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-purchases__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.customer-purchases__list li {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 0.75rem;
  align-items: center;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}

.customer-purchases__amount {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.customer-purchases__empty {
  opacity: 0.7;
}

.customer-purchases__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
