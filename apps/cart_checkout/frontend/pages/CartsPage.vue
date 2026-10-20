<script setup lang="ts">
// Cart & Checkout → Carts (WORKBOOK «Pantallas · Carritos»; CART_CHECKOUT-F01, F05, F06, F12): the live
// `cart_checkout.cart.list` in a server-side DataTable with the old table's Session, Email, Status, Items
// and Total, «Search session or email…», filters per column (items and total typed in the unit the column
// shows), newest first, 50 a page, list or cards. «New cart» opens the form; each row offers «Abandon»
// (an active cart) and «Delete» (confirmed), only to whoever may; a refusal shows above the table. Changes
// come back through the stream. There is no screen for a cart's lines (as the old one): the assistant or
// the API add them.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
  useConfirm,
} from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import CartFormModal from '../components/CartFormModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { CART_TONE, formatMoney, formatQuantity, toMinor, toQuantity } from '../lib/format';
import type { CartListIn, CartOut, CartStatus } from '../operations';
import { cartCheckoutTabs } from '../tabs';

const STATUSES: readonly CartStatus[] = ['active', 'abandoned', 'converted', 'expired'];

const session = useSession();
const t = useT();
const locale = useLocale();
const { confirm } = useConfirm();
const canManage = computed(() => session.can('cart_checkout.manage_cart'));

const table = useServerTable({ sort: '-created_at' });
const filters = ref<DataTableFilters>({});

/** The table's filters as the query takes them: fragments, the status, and the ranges in the unit the
 *  column shows (units of items; the total in the business's currency, to minor units). */
const query = computed<Partial<CartListIn>>(() => {
  const f = filters.value;
  const out: Partial<CartListIn> = {
    ...(f.session_token ? { session_token: f.session_token } : {}),
    ...(f.customer_email ? { customer_email: f.customer_email } : {}),
    ...(f.status ? { status: f.status as CartStatus } : {}),
  };
  const bounds = {
    total_items_min: toQuantity(f.total_items_from),
    total_items_max: toQuantity(f.total_items_to),
    total_amount_min: toMinor(f.total_amount_from),
    total_amount_max: toMinor(f.total_amount_to),
  };
  for (const [key, value] of Object.entries(bounds)) if (value !== undefined) Object.assign(out, { [key]: value });
  return out;
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'cart_checkout.cart.list',
  () => ({ ...query.value, ...table.query.value }),
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<CartOut>[]>(() => [
  { key: 'session_token', label: t('cart_checkout.carts.columns.session'), sortable: true, priority: 'high', filter: { type: 'text' } },
  {
    key: 'customer_email',
    label: t('cart_checkout.carts.columns.email'),
    sortable: true,
    format: (_, row) => row.customer_email || '—',
    filter: { type: 'text' },
  },
  {
    key: 'status',
    label: t('cart_checkout.carts.columns.status'),
    sortable: true,
    cell: 'status',
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`cart_checkout.cartStatus.${value}`) })) },
  },
  {
    key: 'total_items',
    label: t('cart_checkout.carts.columns.items'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatQuantity(row.total_items, locale.value),
    filter: { type: 'range' },
  },
  {
    key: 'total_amount',
    label: t('cart_checkout.carts.columns.total'),
    sortable: true,
    align: 'right',
    format: (_, row) => formatMoney(row.total_amount, locale.value, row.currency),
    filter: { type: 'range' },
  },
]);

// Row actions
const abandon = useCommand('cart_checkout.cart.mark_abandoned');
const remove = useCommand('cart_checkout.cart.delete');
const rowError = ref<ApiError | null>(null);
/** The row whose action is running: a second tap meanwhile does nothing (one command per tap). */
const busy = ref<string | null>(null);

const actions = computed<DataTableAction<CartOut>[]>(() => [
  {
    id: 'abandon',
    label: t('cart_checkout.carts.actions.abandon'),
    icon: 'close-circle-outline',
    color: 'warning',
    loading: (row) => busy.value === row.id,
    hidden: (row) => row.status !== 'active' || !canManage.value,
  },
  {
    id: 'delete',
    label: t('cart_checkout.carts.actions.delete'),
    icon: 'trash-outline',
    color: 'danger',
    loading: (row) => busy.value === row.id,
    hidden: () => !canManage.value,
  },
]);

async function runOn(row: CartOut, command: typeof abandon | typeof remove): Promise<void> {
  busy.value = row.id;
  try {
    await command.run({ cart_id: row.id });
  } catch {
    rowError.value = command.error.value;
  } finally {
    busy.value = null;
  }
}

async function askDelete(row: CartOut): Promise<void> {
  const yes = await confirm({
    title: t('cart_checkout.carts.deleteConfirm.title', { session: row.session_token }),
    message: t('cart_checkout.carts.deleteConfirm.message'),
    confirmLabel: t('cart_checkout.carts.deleteConfirm.confirm'),
    cancelLabel: t('cart_checkout.carts.deleteConfirm.cancel'),
    tone: 'danger',
  });
  if (yes && !busy.value) await runOn(row, remove);
}

async function onAction({ actionId, row }: { actionId: string; row: CartOut }): Promise<void> {
  rowError.value = null;
  if (busy.value) return;
  if (actionId === 'abandon') await runOn(row, abandon);
  else if (actionId === 'delete') await askDelete(row);
}

// The form
const formOpen = ref(false);

/** A new cart heads the first page (newest first): the search, the filters and the order stay. */
function onCreated(): void {
  table.goToPage(0);
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
      testid="cart-checkout-carts"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="cart-checkout-carts-row-error"
      :heading="t('cart_checkout.carts.actionError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="cart-checkout-carts"
      server-side
      searchable
      fill
      :filters="filters"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: CartOut) => row.customer_email || row.session_token"
      :card-icon="() => 'cart-outline'"
      :entity-label="{ one: $t('cart_checkout.carts.entity.one'), many: $t('cart_checkout.carts.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('cart_checkout.carts.loadError') : undefined"
      :addable="canManage"
      :actions="actions"
      :search-placeholder="$t('cart_checkout.carts.search')"
      :labels="{
        add: $t('cart_checkout.carts.new'),
        loadError: $t('cart_checkout.carts.loadError'),
        retry: $t('cart_checkout.live.retry'),
        loading: $t('cart_checkout.loading'),
      }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="formOpen = true"
      @action="onAction"
      @retry="refresh()"
    >
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="CART_TONE[row.status as CartStatus]"
          :label="t(`cart_checkout.cartStatus.${row.status}`)"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="cart-checkout-carts-empty"
          icon="cart-outline"
          :heading="table.filtered.value ? $t('cart_checkout.noResults') : $t('cart_checkout.carts.empty')"
          :message="table.filtered.value ? $t('cart_checkout.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <CartFormModal
      v-model:open="formOpen"
      @created="onCreated"
    />
  </AppPage>
</template>
