<script setup lang="ts">
// Cart & Checkout → Orders (WORKBOOK «Pantallas · Pedidos»; CART_CHECKOUT-F09 to F12): the live
// `cart_checkout.order.list` in a server-side DataTable with the old table's Order, Email, Status, Payment
// and Total (in the order's own currency), «Search order or email…», filters per column behind the toolbar's
// funnel (as the old one; the total typed in the business's currency, its country's: flow
// cart-checkout-business-currency), newest first, 50 a page, list or cards. Each row offers the step it can take —
// «Mark paid», «Complete», «Fail» (asks for the reason) —, only to whoever may; a refusal shows above the
// table. No «add»: an order is born from a cart (CART_CHECKOUT-F08). «Paid» is a mark: nothing here charges
// or is fiscal.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import FailOrderModal from '../components/FailOrderModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { amountExample, formatMoney, ORDER_TONE, recordMoney, TOTAL_BOUNDS, toMinor, unreadableTotals, useBusinessMoney } from '../lib/format';
import type { OrderListIn, OrderOut, OrderStatus } from '../operations';
import { cartCheckoutTabs } from '../tabs';

const STATUSES: readonly OrderStatus[] = ['initiated', 'paid', 'failed', 'completed'];
/** Where an order may still fail from (the server's FAILABLE). */
const FAILABLE: readonly OrderStatus[] = ['initiated', 'paid'];

const session = useSession();
const t = useT();
const locale = useLocale();
const canCheckout = computed(() => session.can('cart_checkout.checkout'));

const table = useServerTable({ sort: '-created_at' });
const filters = ref<DataTableFilters>({});
/** The business's currency (its country's): the Total filter is typed in it. Unknown until it answers. */
const money = useBusinessMoney();

/** The table's filters as the query takes them: fragments, the status and the total in minor units of the
 *  business's currency. */
const query = computed<Partial<OrderListIn>>(() => {
  const f = filters.value;
  const out: Partial<OrderListIn> = {
    ...(f.order_number ? { order_number: f.order_number } : {}),
    ...(f.customer_email ? { customer_email: f.customer_email } : {}),
    ...(f.status ? { status: f.status as OrderStatus } : {}),
    ...(f.payment_method ? { payment_method: f.payment_method } : {}),
  };
  const min = toMinor(f.total_amount_from, money.value);
  const max = toMinor(f.total_amount_to, money.value);
  if (min !== undefined) out.total_amount_min = min;
  if (max !== undefined) out.total_amount_max = max;
  return out;
});

/** An end of «Total» it cannot read as an amount, said under its box (it filters nothing). */
const filterErrors = computed<Record<string, string>>(() =>
  Object.fromEntries(
    unreadableTotals(filters.value, money.value).map((name) => [name, t('cart_checkout.amountInvalid', { example: amountExample(locale.value, money.value) })]),
  ),
);

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

// A Total typed before the business answered is read again in its currency when it does, from the first page.
watch([() => money.value?.currency, () => money.value?.decimals], () => {
  if (TOTAL_BOUNDS.some((name) => filters.value[name])) onFilters(filters.value);
});

const { data: result, status, error, refresh } = useLiveList(
  'cart_checkout.order.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<OrderOut>[]>(() => [
  {
    key: 'order_number',
    label: t('cart_checkout.orders.columns.order'),
    sortable: true,
    priority: 'high',
    // A whole «OS-AAAAMMDD-NNNN» at any width: cut, two orders of a day read the same.
    width: 'minmax(10.5rem, 1fr)',
    filter: { type: 'text' },
  },
  { key: 'customer_email', label: t('cart_checkout.orders.columns.email'), sortable: true, filter: { type: 'text' } },
  {
    key: 'status',
    label: t('cart_checkout.orders.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`cart_checkout.orderStatus.${value}`) })) },
  },
  {
    key: 'payment_method',
    label: t('cart_checkout.orders.columns.payment'),
    sortable: true,
    format: (_, row) => row.payment_method || '—',
    filter: { type: 'text' },
  },
  {
    key: 'total_amount',
    label: t('cart_checkout.orders.columns.total'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatMoney(row.total_amount, locale.value, recordMoney(row)),
    // Typed as an amount (pm#521): a text box with the decimal keyboard, so «1.250,50» can be pasted.
    filter: { type: 'range', amount: true },
  },
]);

// Row actions
const steps = {
  pay: useCommand('cart_checkout.order.mark_paid'),
  complete: useCommand('cart_checkout.order.complete'),
};
const rowError = ref<ApiError | null>(null);
/** The row whose step is running: a second tap meanwhile does nothing (one command per tap). */
const busy = ref<string | null>(null);
const failing = ref<OrderOut | null>(null);
const failOpen = ref(false);

const actions = computed<DataTableAction<OrderOut>[]>(() => [
  {
    id: 'pay',
    label: t('cart_checkout.orders.actions.markPaid'),
    icon: 'card-outline',
    color: 'primary',
    loading: (row) => busy.value === row.id,
    hidden: (row) => row.status !== 'initiated' || !canCheckout.value,
  },
  {
    id: 'complete',
    label: t('cart_checkout.orders.actions.complete'),
    icon: 'checkmark-circle-outline',
    color: 'success',
    loading: (row) => busy.value === row.id,
    hidden: (row) => row.status !== 'paid' || !canCheckout.value,
  },
  {
    id: 'fail',
    label: t('cart_checkout.orders.actions.fail'),
    icon: 'close-outline',
    color: 'danger',
    hidden: (row) => !FAILABLE.includes(row.status) || !canCheckout.value,
  },
]);

async function onAction({ actionId, row }: { actionId: string; row: OrderOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'fail') {
    failing.value = row;
    failOpen.value = true;
    return;
  }
  if ((actionId !== 'pay' && actionId !== 'complete') || busy.value) return;
  const command = steps[actionId];
  busy.value = row.id;
  try {
    await command.run({ order_id: row.id });
  } catch {
    rowError.value = command.error.value;
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <AppPage
    :title="$t('cart_checkout.title')"
    content-layout="fill"
    :tabs="cartCheckoutTabs($t)"
    :tabs-label="$t('cart_checkout.tabs.label')"
  >
    <PageNotices
      testid="cart-checkout-orders"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="cart-checkout-orders-row-error"
      :heading="t('cart_checkout.orders.actionError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="cart-checkout-orders"
      fill
      server-side
      searchable
      filterable
      :filters="filters"
      :filter-errors="filterErrors"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: OrderOut) => row.order_number"
      :card-icon="() => 'receipt-outline'"
      :entity-label="{ one: $t('cart_checkout.orders.entity.one'), many: $t('cart_checkout.orders.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('cart_checkout.orders.loadError') : undefined"
      :addable="false"
      :actions="actions"
      :search-placeholder="$t('cart_checkout.orders.search')"
      :labels="{
        loadError: $t('cart_checkout.orders.loadError'),
        retry: $t('cart_checkout.live.retry'),
        loading: $t('cart_checkout.loading'),
      }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <span class="cart-checkout-status">
          <StatusPill
            size="sm"
            :tone="ORDER_TONE[row.status as OrderStatus]"
            :label="t(`cart_checkout.orderStatus.${row.status}`)"
          />
          <small
            v-if="row.status === 'failed' && row.failure_reason"
            class="cart-checkout-status__reason"
          >{{ t('cart_checkout.orders.failureReason', { reason: row.failure_reason }) }}</small>
        </span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="cart-checkout-orders-empty"
          icon="receipt-outline"
          :heading="table.filtered.value ? $t('cart_checkout.noResults') : $t('cart_checkout.orders.empty')"
          :message="table.filtered.value ? $t('cart_checkout.noResultsMessage') : $t('cart_checkout.orders.emptyMessage')"
        />
      </template>
    </DataTable>
    <FailOrderModal
      v-model:open="failOpen"
      :order="failing"
    />
  </AppPage>
</template>

<style scoped>
.cart-checkout-status {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  max-width: 100%;
}

/* A failed order's reason wraps inside its cell: cut, it read «Card declin» at 834 px. */
.cart-checkout-status__reason {
  max-width: 100%;
  color: var(--ion-color-medium);
  font-size: 0.8em;
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
