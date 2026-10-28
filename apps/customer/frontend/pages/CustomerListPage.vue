<script setup lang="ts">
// Customers → Customers (WORKBOOK «Pantallas · Clientes»; CUSTOMER-F01, F02, F07, F08, F09): the four
// figures, then the live `customer.customer.list` in a server-side DataTable — Name, Email, Phone,
// Stage, Spent —, search on the server (name, phone, email, tax id and company; a phone however it is
// typed), filters behind the table's funnel, sort by any column, 50 a page. «Add» and «Import CSV» to whoever manages cards,
// «Export CSV» to whoever exports; a row opens the card; «Delete» on a row asks first. Nothing here
// refetches: a write anywhere re-runs the queries on the server and the results arrive by the stream.
import {
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilterField,
  type DataTableFilters,
  DataTable,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import CustomerCreateModal from '../components/CustomerCreateModal.vue';
import CustomerDeleteDialog from '../components/CustomerDeleteDialog.vue';
import CustomerExportButton from '../components/CustomerExportButton.vue';
import CustomerImportButton from '../components/CustomerImportButton.vue';
import CustomerStats from '../components/CustomerStats.vue';
import ImportReport from '../components/ImportReport.vue';
import { STAGES } from '../lib/customerForm';
import { filterParams, filtersInUse, SOURCES, unreadableAmounts } from '../lib/customerFilters';
import { formatMoney, useBusinessMoney } from '../lib/money';
import { formatPhone } from '../lib/phoneDisplay';
import { customerTabs } from '../lib/tabs';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import { useCustomerImport } from '../lib/useCustomerImport';
import { type SortDir, useListState } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';
import type { CustomerListIn, CustomerRow, CustomerSort } from '../operations';

const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('customer.manage'));
const canExport = computed(() => session.can('customer.export'));
const canDelete = computed(() => session.can('customer.delete'));
const { t, locale } = useCustomerI18n();

const list = useListState({ sort: 'name' });
/** The business's currency (its country's): «Spent» is painted and typed in it (customer-business-currency). */
const money = useBusinessMoney();
/** The table's filters (its funnel), as typed: «Spent» in the business's money. A filter not in use is absent. */
const filters = ref<DataTableFilters>({});
// Only the filters that really apply narrow the list (an amount it cannot read does not); an amount typed before
// the business answered is read again in its currency when it does.
watch([filters, () => money.value?.currency, () => money.value?.decimals], () =>
  list.restart({ narrowed: filtersInUse(filters.value, money.value) > 0 }),
);

/** The search, sort and filters of every window of the list (≤ 100 rows each: `useLiveList`). */
const query = computed(() => ({ ...filterParams(filters.value, money.value), ...list.base.value }) as CustomerListIn);
const { data: result, status, error, refresh } = useLiveList('customer.customer.list', () => query.value, list.windows);
list.followResult(result);

const inactive = computed(() => error.value?.code === 'app_inactive');
/** What «Export CSV» exports: the search and filters of the table, every page. */
const exportFilters = computed(() => query.value);

const columns = computed<DataTableColumn<CustomerRow>[]>(() => [
  { key: 'name', label: t('customer.list.columns.name'), sortable: true, priority: 'high', cell: 'name' },
  { key: 'email', label: t('customer.list.columns.email'), sortable: true },
  { key: 'phone', label: t('customer.list.columns.phone'), sortable: true, cell: 'phone' },
  {
    key: 'lifecycle_stage',
    label: t('customer.list.columns.stage'),
    sortable: true,
    cell: 'stage',
    filter: { type: 'select', options: STAGES.map((stage) => ({ value: stage, label: t(`customer.stage.${stage}`) })) },
  },
  {
    key: 'total_spent',
    label: t('customer.list.columns.spent'),
    sortable: true,
    align: 'right',
    cell: 'spent',
    filter: { type: 'range', amount: true, keys: ['spent_from', 'spent_to'] },
  },
]);

/** The filters with no column of their own, after the columns' (Stage, Spent). */
const filterFields = computed<DataTableFilterField[]>(() => [
  {
    type: 'select',
    key: 'source',
    label: t('customer.list.filters.source'),
    options: SOURCES.map((origin) => ({ value: origin, label: t(`customer.source.${origin}`) })),
  },
  {
    type: 'select',
    key: 'is_active',
    label: t('customer.list.filters.active'),
    options: [
      { value: 'true', label: t('customer.list.filters.activeOnly') },
      { value: 'false', label: t('customer.list.filters.inactiveOnly') },
    ],
  },
]);

/** An amount of «Spent» it cannot read, said under its field (it does not filter). */
const filterErrors = computed(() =>
  Object.fromEntries(unreadableAmounts(filters.value, money.value).map((name) => [name, t('customer.filters.amountInvalid')])),
);

const actions = computed<DataTableAction<CustomerRow>[]>(() => [
  { id: 'open', label: t('customer.list.view'), icon: 'ion:chevron-forward-outline', pinned: true },
  ...(canDelete.value
    ? [{ id: 'delete', label: t('customer.common.delete'), icon: 'ion:trash-outline', color: 'danger' }]
    : []),
]);

const creating = ref(false);
const deleting = ref<{ id: string; name: string } | null>(null);
const importer = useCustomerImport();

const open = (row: CustomerRow) => router.push(`/customer/customers/${row.id}`);

function onAction(event: { actionId: string; row: CustomerRow }): void {
  if (event.actionId === 'open') void open(event.row);
  if (event.actionId === 'delete') deleting.value = { id: event.row.id, name: event.row.name };
}

function onSort(next: { sort: string; dir: SortDir }): void {
  list.setSort({ sort: next.sort as CustomerSort, dir: next.dir });
}
</script>

<template>
  <AppPage
    :title="$t('customer.list.title')"
    content-layout="fill"
    :tabs="customerTabs($t)"
    :tabs-label="$t('customer.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="customer-list-reconnecting"
    >
      {{ $t('customer.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="customer-list-inactive"
      :heading="$t('customer.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <template v-else>
      <CustomerStats />
      <InlineFeedback
        v-if="importer.importing.value"
        tone="info"
        data-testid="customer-list-importing"
      >
        {{ $t('customer.importCsv.importing') }}
      </InlineFeedback>
      <InlineFeedback
        v-if="importer.problem.value"
        tone="warning"
        data-testid="customer-list-import-problem"
        dismissible
        @dismiss="importer.dismiss()"
      >
        {{
          importer.problem.value === 'noRows' ? $t('customer.importCsv.noRows') : $t('customer.importCsv.unreadable')
        }}
      </InlineFeedback>
      <ImportReport
        v-if="importer.report.value"
        :report="importer.report.value"
        @close="importer.dismiss()"
      />
      <DataTable
        v-model:search="list.search.value"
        v-model:filters="filters"
        testid="customer-list"
        fill
        server-side
        searchable
        filterable
        :filter-fields="filterFields"
        :filter-errors="filterErrors"
        row-clickable
        :rows="result?.rows ?? []"
        :total="result?.total ?? 0"
        :page="list.page.value"
        :page-size="list.pageSize.value"
        :sort="list.sort.value"
        :sort-dir="list.dir.value"
        :views="['table', 'cards']"
        :card-title="(row: CustomerRow) => row.name"
        card-title-column="name"
        :card-icon="() => 'ion:person-outline'"
        :entity-label="{ one: $t('customer.list.entity.one'), many: $t('customer.list.entity.many') }"
        :loading="status === 'loading'"
        :error="status === 'error' ? error?.message : undefined"
        :addable="canManage"
        :actions="actions"
        :search-placeholder="$t('customer.list.search')"
        :labels="{ add: $t('customer.common.add'), loadError: $t('customer.list.loadError'), retry: $t('customer.live.retry') }"
        :columns="columns"
        @page-change="list.goToPage"
        @load-more="list.loadMore"
        @page-size-change="list.setPageSize"
        @sort-change="onSort"
        @row-click="open"
        @action="onAction"
        @add="creating = true"
        @retry="refresh()"
      >
        <template #toolbar>
          <CustomerImportButton
            v-if="canManage"
            :busy="importer.importing.value"
            @pick="importer.importFile"
          />
          <CustomerExportButton
            v-if="canExport"
            :filters="exportFilters"
          />
        </template>
        <template #name="{ row }">
          <span
            data-testid="customer-list-name"
            :title="row.name"
          >{{ row.name }}</span>
        </template>
        <template #phone="{ row }">
          <span data-testid="customer-list-phone">{{ formatPhone(row.phone) }}</span>
        </template>
        <template #stage="{ row }">
          <span data-testid="customer-list-stage">{{ $t(`customer.stage.${row.lifecycle_stage}`) }}</span>
        </template>
        <template #spent="{ row }">
          <span data-testid="customer-list-spent">{{ formatMoney(row.total_spent, locale, money) }}</span>
        </template>
        <template #empty>
          <EmptyState
            data-testid="customer-list-empty"
            icon="people-outline"
            :heading="list.filtered.value ? $t('customer.list.noResults') : $t('customer.list.empty')"
            :message="
              list.filtered.value
                ? $t('customer.list.noResultsMessage')
                : canManage
                  ? $t('customer.list.emptyMessage')
                  : undefined
            "
          />
        </template>
      </DataTable>
    </template>
    <CustomerCreateModal
      v-if="canManage"
      v-model:open="creating"
    />
    <CustomerDeleteDialog
      v-if="canDelete"
      v-model:customer="deleting"
    />
  </AppPage>
</template>
