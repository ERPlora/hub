<script setup lang="ts">
// A price list's detail (WORKBOOK «Pantallas · Tarifa (detalle)»; PRICING-F03 to F08), the screen the old
// module did not have: the live `pricing.price_list.get` — Code with «General», Customer group, Currency,
// Tax, Validity and Status, with Edit, Make general and Deactivate / Activate for whoever manages — and
// its «Prices», the live `pricing.price_item.list` of this list in a server-side DataTable: Item, Type,
// SKU, From (with the product's unit), Price (in the list's currency) and Catalog price, «Search product
// or service…», a Type filter, 50 a page by item. «+» adds a price; a row is edited or removed (asking
// first). A list that does not exist says so, with Back. Its prices are in its own currency; the catalog's,
// in the business's (its country's; a bare figure until it answers), and only a list in the business's
// currency can be made general.
import {
  ConfirmDialog,
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, ref } from 'vue';

import ListConfirm, { type ListAction } from '../components/ListConfirm.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import PriceItemFormModal from '../components/PriceItemFormModal.vue';
import PriceListFormModal from '../components/PriceListFormModal.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatMoney, formatQuantity, listMoney, useBusinessMoney, validityLabel } from '../lib/format';
import { groupName, taxBasisLabel } from '../lib/rules';
import type { Kind, PriceItemListIn, PriceItemOut } from '../operations';

const KINDS: readonly Kind[] = ['product', 'service'];

const props = defineProps<{ id: string }>();

const session = useSession();
const t = useT();
const locale = useLocale();
const canManage = computed(() => session.can('pricing.manage'));

// The list
const { data: list, status: listStatus, error: listError } = useLive('pricing.price_list.get', () => ({ id: props.id }));
const missing = computed(() => listError.value?.code === 'pricing.price_list_not_found' || listError.value?.code === 'not_found');
const money = computed(() => listMoney(list.value?.currency));
const business = useBusinessMoney();

// Its prices
const table = useServerTable({ sort: 'name' });
const filters = ref<DataTableFilters>({});
const query = computed<Partial<PriceItemListIn>>(() => ({
  price_list_id: props.id,
  ...(filters.value.kind ? { kind: filters.value.kind as Kind } : {}),
}));

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  table.restart({ narrowed: Object.keys(now).length > 0 });
}

const { data: result, status, error, refresh } = useLiveList(
  'pricing.price_item.list',
  () => ({ ...query.value, ...table.query.value }) as PriceItemListIn,
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value) ?? blockingError(listError.value));

const quantityLabel = (row: PriceItemOut): string =>
  row.unit ? `${formatQuantity(row.min_quantity, locale.value)} ${row.unit}` : formatQuantity(row.min_quantity, locale.value);

const columns = computed<DataTableColumn<PriceItemOut>[]>(() => [
  { key: 'name', label: t('pricing.items.columns.name'), sortable: true, priority: 'high' },
  {
    key: 'kind',
    label: t('pricing.items.columns.kind'),
    format: (_, row) => t(`pricing.items.kind.${row.kind}`),
    filter: { type: 'select', options: KINDS.map((value) => ({ value, label: t(`pricing.items.kind.${value}`) })) },
  },
  { key: 'sku', label: t('pricing.items.columns.sku'), priority: 'low', format: (_, row) => row.sku ?? t('pricing.none') },
  { key: 'min_quantity', label: t('pricing.items.columns.minQuantity'), sortable: true, align: 'right', format: (_, row) => quantityLabel(row) },
  { key: 'price', label: t('pricing.items.columns.price'), sortable: true, align: 'right', format: (_, row) => formatMoney(row.price, locale.value, money.value) },
  {
    key: 'base_price',
    label: t('pricing.items.columns.basePrice'),
    align: 'right',
    priority: 'low',
    format: (_, row) => (row.base_price === null ? t('pricing.none') : formatMoney(row.base_price, locale.value, business.value)),
  },
]);

/** A deactivated list keeps its prices as they are (the server refuses adding or changing one); they can
 *  still be removed. */
const canChangePrices = computed(() => canManage.value && !!list.value?.is_active);

const actions = computed<DataTableAction<PriceItemOut>[]>(() => [
  ...(canChangePrices.value ? [{ id: 'edit', label: t('pricing.items.actions.edit'), icon: 'create-outline' }] : []),
  ...(canManage.value ? [{ id: 'remove', label: t('pricing.items.actions.remove'), icon: 'trash-outline', color: 'danger' }] : []),
]);

// Forms, confirmations and actions
const listFormOpen = ref(false);
const confirmAction = ref<ListAction | null>(null);
const activate = useCommand('pricing.price_list.activate');
const actionError = ref<ApiError | null>(null);

const editingItem = ref<PriceItemOut | null>(null);
const itemFormOpen = ref(false);
const removing = ref<PriceItemOut | null>(null);
const removeOpen = ref(false);
const remove = useCommand('pricing.price_item.remove');

const canMakeDefault = computed(
  () =>
    !!list.value &&
    list.value.is_active &&
    !list.value.is_default &&
    list.value.customer_group_id === null &&
    list.value.currency === business.value?.currency,
);

async function activateList(): Promise<void> {
  actionError.value = null;
  try {
    await activate.run({ id: props.id });
  } catch {
    actionError.value = activate.error.value;
  }
}

function openItemForm(row: PriceItemOut | null): void {
  editingItem.value = row;
  itemFormOpen.value = true;
}

async function confirmRemove(): Promise<void> {
  if (!removing.value) return;
  try {
    await remove.run({ id: removing.value.id });
  } catch {
    return; // The dialog says why.
  }
  removeOpen.value = false;
}

function onAction({ actionId, row }: { actionId: string; row: PriceItemOut }): void {
  if (actionId === 'edit') openItemForm(row);
  if (actionId === 'remove') {
    remove.error.value = null;
    removing.value = row;
    removeOpen.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="list?.name ?? $t('pricing.title')"
    back-href="/pricing/lists"
  >
    <template
      v-if="canManage && list"
      #actions
    >
      <ion-button
        data-testid="pricing-detail-edit"
        @click="listFormOpen = true"
      >
        {{ $t('pricing.lists.actions.edit') }}
      </ion-button>
      <ion-button
        v-if="canMakeDefault"
        data-testid="pricing-detail-default"
        @click="confirmAction = 'default'"
      >
        {{ $t('pricing.lists.actions.makeDefault') }}
      </ion-button>
      <ion-button
        v-if="list.is_active && !list.is_default"
        data-testid="pricing-detail-deactivate"
        color="danger"
        @click="confirmAction = 'deactivate'"
      >
        {{ $t('pricing.lists.actions.deactivate') }}
      </ion-button>
      <ion-button
        v-if="!list.is_active"
        data-testid="pricing-detail-activate"
        :disabled="activate.pending.value"
        @click="activateList"
      >
        {{ $t('pricing.lists.actions.activate') }}
      </ion-button>
    </template>

    <div class="pricing-detail">
      <PageNotices
        testid="pricing-detail"
        :status="listStatus"
        :error="missing ? null : listError"
      />
      <InlineFeedback
        v-if="missing"
        tone="warning"
        data-testid="pricing-detail-not-found"
        :heading="$t('pricing.detail.notFound')"
      >
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            router-link="/pricing/lists"
            router-direction="back"
          >
            {{ $t('pricing.detail.backLabel') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <InlineFeedback
        v-if="actionError"
        tone="danger"
        dismissible
        data-testid="pricing-detail-action-error"
        :heading="$t('pricing.lists.rowError')"
        @dismiss="actionError = null"
      >
        {{ actionError.message }}
      </InlineFeedback>
      <div
        v-if="!list && listStatus === 'loading'"
        class="ion-text-center ion-padding"
      >
        <ion-spinner data-testid="pricing-detail-loading" />
      </div>

      <template v-if="list && !missing">
        <dl
          class="pricing-summary"
          data-testid="pricing-detail-summary"
          :aria-label="$t('pricing.detail.summary')"
        >
          <div>
            <dt>{{ $t('pricing.detail.code') }}</dt>
            <dd data-testid="pricing-detail-code">
              <span class="pricing-summary__code"><span>{{ list.code }}</span> <StatusPill
                v-if="list.is_default"
                size="sm"
                tone="info"
                :label="t('pricing.lists.default')"
              /></span>
            </dd>
          </div>
          <div>
            <dt>{{ $t('pricing.detail.group') }}</dt>
            <dd>{{ list.is_default ? t('pricing.lists.everybody') : groupName(list.customer_group_id, list.customer_group_name, t) }}</dd>
          </div>
          <div>
            <dt>{{ $t('pricing.detail.currency') }}</dt>
            <dd>{{ list.currency }}</dd>
          </div>
          <div>
            <dt>{{ $t('pricing.detail.tax') }}</dt>
            <dd>{{ taxBasisLabel(list.tax_included, t) }}</dd>
          </div>
          <div>
            <dt>{{ $t('pricing.detail.validity') }}</dt>
            <dd>{{ validityLabel(list.valid_from, list.valid_until, t, locale) }}</dd>
          </div>
          <div>
            <dt>{{ $t('pricing.detail.state') }}</dt>
            <dd>
              <StatusPill
                size="sm"
                :tone="list.is_active ? 'success' : 'neutral'"
                :label="t(list.is_active ? 'pricing.state.active' : 'pricing.state.inactive')"
              />
            </dd>
          </div>
        </dl>

        <h2 class="pricing-detail__heading">
          {{ $t('pricing.items.heading') }}
        </h2>
        <PageNotices
          testid="pricing-items"
          :status="status"
          :error="error"
        />
        <DataTable
          v-if="!blocked"
          v-model:search="table.search.value"
          testid="pricing-items"
          server-side
          searchable
          filterable
          :filters="filters"
          :rows="result?.rows ?? []"
          :total="result?.total ?? 0"
          :page="table.page.value"
          :page-size="table.pageSize.value"
          :sort="table.sort.value"
          :sort-dir="table.dir.value"
          :views="['table', 'cards']"
          :card-title="(row: PriceItemOut) => row.name"
          :entity-label="{ one: $t('pricing.items.entity.one'), many: $t('pricing.items.entity.many') }"
          :loading="status === 'loading'"
          :error="status === 'error' && !blocked ? $t('pricing.items.loadError') : undefined"
          :addable="canChangePrices"
          :row-clickable="canChangePrices"
          :actions="actions"
          :search-placeholder="$t('pricing.items.search')"
          :labels="{ add: $t('pricing.items.new'), loadError: $t('pricing.items.loadError'), retry: $t('pricing.live.retry') }"
          :columns="columns"
          @filters-change="onFilters"
          @page-change="table.goToPage"
          @load-more="table.loadMore"
          @page-size-change="table.setPageSize"
          @sort-change="table.setSort"
          @row-click="openItemForm"
          @add="openItemForm(null)"
          @action="onAction"
          @retry="refresh()"
        >
          <template #empty>
            <EmptyState
              data-testid="pricing-items-empty"
              icon="pricetag"
              :heading="table.filtered.value ? $t('pricing.noResults') : $t('pricing.items.empty')"
              :message="table.filtered.value ? $t('pricing.noResultsMessage') : undefined"
            />
          </template>
        </DataTable>
      </template>
    </div>

    <template v-if="canManage">
      <PriceListFormModal
        v-model:open="listFormOpen"
        :price-list="list ?? null"
      />
      <ListConfirm
        v-model:action="confirmAction"
        :list="list ?? null"
      />
      <PriceItemFormModal
        v-model:open="itemFormOpen"
        :price-list-id="id"
        :currency="list?.currency"
        :item="editingItem"
      />
      <ConfirmDialog
        v-model:open="removeOpen"
        testid="pricing-items-remove"
        tone="danger"
        :title="removing ? t('pricing.items.removeConfirm.title', { name: removing.name }) : ''"
        :message="removing ? t('pricing.items.removeConfirm.message', { name: removing.name, quantity: quantityLabel(removing) }) : ''"
        :confirm-label="t('pricing.items.removeConfirm.confirm')"
        :cancel-label="t('pricing.cancel')"
        :pending="remove.pending.value"
        :error="remove.error.value"
        @confirm="confirmRemove"
        @cancel="removeOpen = false"
      />
    </template>
  </AppPage>
</template>

<style scoped>
.pricing-detail {
  display: grid;
  gap: 10px;
}
.pricing-summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 12px 20px;
  margin: 0;
  padding: 14px 16px;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 10px;
  background: var(--ion-item-background, #fff);
}
.pricing-summary dt {
  font-size: 0.78rem;
  color: var(--ion-color-medium, #5c594f);
}
.pricing-summary > div {
  min-width: 0;
}
.pricing-summary dd {
  margin: 2px 0 0;
  font-weight: 600;
  /* A code of up to 50 characters breaks inside its cell instead of running over the next one. */
  overflow-wrap: anywhere;
}
.pricing-summary__code {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
.pricing-summary__code > span:first-child {
  min-width: 0;
}
.pricing-detail__heading {
  margin: 0.5rem 0 0;
  font-size: 1rem;
  font-weight: 600;
  color: var(--ion-color-medium, #5c594f);
}
</style>
