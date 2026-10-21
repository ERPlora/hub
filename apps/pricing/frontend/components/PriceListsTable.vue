<script setup lang="ts">
// Price Lists → «Price lists» (WORKBOOK «Pantallas · Tarifas»; PRICING-F01 to F05): the live
// `pricing.price_list.list` in a server-side DataTable — Code (with «General»), Name, Currency, Customer
// group («Everybody» for the general one, «Deleted group» when Customers deleted it), Tax, Validity, Prices and Status —, «Search code or name…»,
// column filters behind the funnel (Status opens on the active ones), list or cards, 50 a page by name. A row and its «Open»
// open the list's detail; whoever manages gets «+» (New price list), Edit, Make general (an active list
// in euros without group that is not general), Deactivate (not the general one, asking first) and Activate.
import {
  DataTable,
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  EmptyState,
  InlineFeedback,
  StatusPill,
} from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { BUSINESS_CURRENCY, validityLabel } from '../lib/format';
import { groupName, taxBasisLabel } from '../lib/rules';
import type { PriceListListIn, PriceListOut, Status, TaxBasis } from '../operations';
import ListConfirm, { type ListAction } from './ListConfirm.vue';
import PageNotices, { blockingError } from './PageNotices.vue';
import PriceListFormModal from './PriceListFormModal.vue';

const BASES: readonly TaxBasis[] = ['business', 'included', 'excluded'];
// The active ones until the person picks another status; the table's own blank option («All») asks for
// every one, so there is no second «All» beside it that meant something else (pm#254).
const STATUSES: readonly Status[] = ['active', 'inactive'];
const DEFAULT_STATUS = 'active';

const session = useSession();
const router = useRouter();
const t = useT();
const locale = useLocale();
const canManage = computed(() => session.can('pricing.manage'));

const table = useServerTable({ sort: 'name' });
const filters = ref<DataTableFilters>({ status: DEFAULT_STATUS });

const query = computed<Partial<PriceListListIn>>(() => {
  const f = filters.value;
  return {
    ...(f.code ? { code: f.code } : {}),
    ...(f.name ? { name: f.name } : {}),
    ...(f.currency ? { currency: f.currency } : {}),
    ...(f.customer_group_id ? { customer_group_id: f.customer_group_id } : {}),
    ...(f.tax_basis ? { tax_basis: f.tax_basis as TaxBasis } : {}),
    status: (f.status || 'all') as Status,
  };
});

function onFilters(now: DataTableFilters): void {
  filters.value = now;
  // The default status narrows nothing the person asked for: an empty answer is still «No price lists.».
  table.restart({ narrowed: Object.entries(now).some(([key, value]) => value && !(key === 'status' && value === DEFAULT_STATUS)) });
}

const { data: result, status, error, refresh } = useLiveList(
  'pricing.price_list.list',
  () => ({ ...query.value, ...table.query.value }) as PriceListListIn,
  () => table.windows.value,
);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

// The group filter offers the business's active groups (a handful).
const { data: groups } = useLive('customer.group.list', { is_active: true, limit: 100 });

function groupLabel(row: PriceListOut): string {
  if (row.is_default) return t('pricing.lists.everybody');
  return groupName(row.customer_group_id, row.customer_group_name, t);
}

const columns = computed<DataTableColumn<PriceListOut>[]>(() => [
  { key: 'code', label: t('pricing.lists.columns.code'), sortable: true, cell: 'code', filter: { type: 'text' } },
  { key: 'name', label: t('pricing.lists.columns.name'), sortable: true, priority: 'high', filter: { type: 'text' } },
  { key: 'currency', label: t('pricing.lists.columns.currency'), sortable: true, filter: { type: 'text' } },
  {
    key: 'customer_group_name',
    label: t('pricing.lists.columns.group'),
    sortable: true,
    format: (_, row) => groupLabel(row),
    filter: {
      type: 'select',
      key: 'customer_group_id',
      options: (groups.value?.rows ?? []).map((group) => ({ value: group.id, label: group.name })),
    },
  },
  {
    key: 'tax_included',
    label: t('pricing.lists.columns.tax'),
    sortable: true,
    format: (_, row) => taxBasisLabel(row.tax_included, t),
    filter: { type: 'select', key: 'tax_basis', options: BASES.map((value) => ({ value, label: t(`pricing.taxBasis.${value}`) })) },
  },
  {
    key: 'validity',
    label: t('pricing.lists.columns.validity'),
    priority: 'low',
    format: (_, row) => validityLabel(row.valid_from, row.valid_until, t, locale.value),
  },
  { key: 'item_count', label: t('pricing.lists.columns.prices'), align: 'right', priority: 'low', format: (_, row) => String(row.item_count) },
  {
    key: 'status',
    label: t('pricing.lists.columns.status'),
    cell: 'status',
    priority: 'low',
    format: (_, row) => t(row.is_active ? 'pricing.state.active' : 'pricing.state.inactive'),
    filter: { type: 'select', options: STATUSES.map((value) => ({ value, label: t(`pricing.status.${value}`) })) },
  },
]);

const actions = computed<DataTableAction<PriceListOut>[]>(() => [
  { id: 'open', label: t('pricing.lists.actions.open'), icon: 'chevron-forward-outline', color: 'primary', showLabel: true, pinned: true },
  ...(canManage.value
    ? [
        { id: 'edit', label: t('pricing.lists.actions.edit'), icon: 'create-outline' },
        {
          id: 'makeDefault',
          label: t('pricing.lists.actions.makeDefault'),
          icon: 'checkmark-circle-outline',
          menuOnly: true,
          hidden: (row: PriceListOut) =>
            row.is_default || !row.is_active || row.customer_group_id !== null || row.currency !== BUSINESS_CURRENCY,
        },
        {
          id: 'deactivate',
          label: t('pricing.lists.actions.deactivate'),
          icon: 'ban-outline',
          color: 'danger',
          menuOnly: true,
          hidden: (row: PriceListOut) => !row.is_active || row.is_default,
        },
        {
          id: 'activate',
          label: t('pricing.lists.actions.activate'),
          icon: 'arrow-undo-outline',
          color: 'success',
          hidden: (row: PriceListOut) => row.is_active,
        },
      ]
    : []),
]);

// The form and the confirmations
const editing = ref<PriceListOut | null>(null);
const formOpen = ref(false);
const confirming = ref<PriceListOut | null>(null);
const confirmAction = ref<ListAction | null>(null);
const activate = useCommand('pricing.price_list.activate');
const rowError = ref<ApiError | null>(null);

function openList(row: PriceListOut): void {
  void router.push(`/pricing/lists/${row.id}`);
}

function openForm(row: PriceListOut | null): void {
  editing.value = row;
  formOpen.value = true;
}

async function onAction({ actionId, row }: { actionId: string; row: PriceListOut }): Promise<void> {
  rowError.value = null;
  if (actionId === 'open') openList(row);
  if (actionId === 'edit') openForm(row);
  if (actionId === 'makeDefault' || actionId === 'deactivate') {
    confirming.value = row;
    confirmAction.value = actionId === 'makeDefault' ? 'default' : 'deactivate';
  }
  if (actionId === 'activate') {
    try {
      await activate.run({ id: row.id });
    } catch {
      rowError.value = activate.error.value;
    }
  }
}
</script>

<template>
  <section class="pricing-section">
    <PageNotices
      testid="pricing-lists"
      :status="status"
      :error="error"
    />
    <InlineFeedback
      v-if="rowError"
      tone="danger"
      dismissible
      data-testid="pricing-lists-row-error"
      :heading="t('pricing.lists.rowError')"
      @dismiss="rowError = null"
    >
      {{ rowError.message }}
    </InlineFeedback>
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="pricing-lists"
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
      :card-title="(row: PriceListOut) => row.name"
      :card-icon="() => 'pricetags-outline'"
      :entity-label="{ one: $t('pricing.lists.entity.one'), many: $t('pricing.lists.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('pricing.lists.loadError') : undefined"
      :addable="canManage"
      row-clickable
      :actions="actions"
      :search-placeholder="$t('pricing.lists.search')"
      :labels="{ add: $t('pricing.lists.new'), loadError: $t('pricing.lists.loadError'), retry: $t('pricing.live.retry') }"
      :columns="columns"
      @filters-change="onFilters"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openList"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #code="{ row }">
        <span class="pricing-code"><span>{{ row.code }}</span> <StatusPill
          v-if="row.is_default"
          size="sm"
          tone="info"
          :label="t('pricing.lists.default')"
        /></span>
      </template>
      <template #status="{ row }">
        <StatusPill
          size="sm"
          :tone="row.is_active ? 'success' : 'neutral'"
          :label="t(row.is_active ? 'pricing.state.active' : 'pricing.state.inactive')"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="pricing-lists-empty"
          icon="pricetags-outline"
          :heading="table.filtered.value ? $t('pricing.noResults') : $t('pricing.lists.empty')"
          :message="table.filtered.value ? $t('pricing.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <PriceListFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :price-list="editing"
    />
    <ListConfirm
      v-if="canManage"
      v-model:action="confirmAction"
      :list="confirming"
    />
  </section>
</template>

<style scoped>
.pricing-section {
  display: grid;
  gap: 8px;
}
.pricing-code {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  max-width: 100%;
}
/* A code of up to 50 characters breaks inside its card on a phone instead of running out of it. */
.pricing-code > span:first-child {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>
