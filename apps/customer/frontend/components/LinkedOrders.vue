<script setup lang="ts">
// «Linked orders» of a card (CUSTOMER-F19): the orders the till linked to this customer (the open
// check, the cart), the latest first, each by its short id and when it was linked; live.
import { formatDateTime } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useCustomerI18n } from '../lib/useCustomerI18n';
import { windowsOf } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';

const props = defineProps<{ customerId: string }>();

const STEP = 50;
const { locale } = useCustomerI18n();

const limit = ref(STEP);
// «Show more» grows what is shown by 50; the server is asked in windows of ≤ 100 (`useLiveList`).
const windows = computed(() => windowsOf(0, limit.value));
const live = useLiveList('customer.order.list', () => ({ customer_id: props.customerId }), windows);
const rows = computed(() => live.data.value?.rows ?? []);
const more = computed(() => (live.data.value ? live.data.value.total > live.data.value.rows.length : false));

/** The last 8 characters of the id: enough to tell orders apart on screen; the whole one in the title. */
const shortId = (id: string): string => id.replace(/-/g, '').slice(-8);
</script>

<template>
  <div
    class="customer-orders"
    data-testid="customer-orders"
  >
    <h3>{{ $t('customer.orders.heading') }}</h3>
    <p
      v-if="live.status.value === 'error' && live.error.value?.code !== 'app_inactive'"
      class="customer-orders__error"
      data-testid="customer-orders-error"
      role="alert"
    >
      {{ $t('customer.orders.loadError') }}: {{ live.error.value?.message }}
    </p>
    <ul
      v-if="rows.length"
      class="customer-orders__list"
    >
      <li
        v-for="row in rows"
        :key="row.order_id"
        data-testid="customer-order"
      >
        <span
          class="customer-orders__id"
          :title="row.order_id"
        >{{ $t('customer.orders.order', { id: shortId(row.order_id) }) }}</span>
        <span class="customer-orders__when">{{ formatDateTime(row.linked_at, locale) }}</span>
      </li>
    </ul>
    <p
      v-else-if="live.data.value"
      class="customer-orders__empty"
      data-testid="customer-orders-empty"
    >
      {{ $t('customer.orders.empty') }}
    </p>
    <ion-button
      v-if="more"
      size="small"
      fill="clear"
      data-testid="customer-orders-more"
      @click="limit += STEP"
    >
      {{ $t('customer.orders.more') }}
    </ion-button>
  </div>
</template>

<style scoped>
.customer-orders h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-orders__list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.customer-orders__list li {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.4rem 0;
  border-bottom: 1px solid var(--ion-border-color, #e7e2d6);
}

.customer-orders__id {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.customer-orders__when {
  opacity: 0.7;
  font-size: 0.85rem;
}

.customer-orders__empty {
  opacity: 0.7;
}

.customer-orders__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
