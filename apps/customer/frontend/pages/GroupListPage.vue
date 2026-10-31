<script setup lang="ts">
// Customers → Groups (WORKBOOK «Pantallas · Grupos»; CUSTOMER-F27): the live `customer.group.list`
// in a server-side DataTable — Name, Description, Customers (live cards in it), Order, Active —,
// «Search group…» and the active filter behind the table's funnel (a group not active stays in the list and is reactivated
// from its edit). «Add» and «Edit» (also a tap on the row) to whoever configures; «Delete» to the
// owner and the admin.
import {
  type DataTableAction,
  type DataTableColumn,
  type DataTableFilters,
  DataTable,
  EmptyState,
  InlineFeedback,
} from '@erplora/ui/components';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import EntityDeleteDialog from '../components/EntityDeleteDialog.vue';
import GroupFormModal from '../components/GroupFormModal.vue';
import { customerTabs } from '../lib/tabs';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import { type SortDir, useListState } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';
import type { GroupListIn, GroupRow } from '../operations';

const session = useSession();
// Whoever manages cards sees it too: without the permission, a manager approves it with their PIN (BASE-F84).
const canConfigure = computed(() => session.can('customer.configure') || session.can('customer.manage'));
const canDelete = computed(() => session.can('customer.delete'));
const { t } = useCustomerI18n();

const list = useListState({ sort: 'name' });
/** The table's filters (its funnel): a filter not in use is absent. */
const filters = ref<DataTableFilters>({});
watch(filters, (now) => list.restart({ narrowed: Object.keys(now).length > 0 }));
const query = computed(
  () =>
    ({
      ...(filters.value.is_active ? { is_active: filters.value.is_active === 'true' } : {}),
      ...list.base.value,
    }) as GroupListIn,
);
const { data: result, status, error, refresh } = useLiveList('customer.group.list', () => query.value, list.windows);
list.followResult(result);
const inactive = computed(() => error.value?.code === 'app_inactive');

const columns = computed<DataTableColumn<GroupRow>[]>(() => [
  { key: 'name', label: t('customer.groups.columns.name'), sortable: true, priority: 'high' },
  { key: 'description', label: t('customer.groups.columns.description'), sortable: true, priority: 'low' },
  { key: 'customer_count', label: t('customer.groups.columns.customers'), sortable: true, align: 'right' },
  { key: 'sort_order', label: t('customer.groups.columns.order'), sortable: true, align: 'right', priority: 'low' },
  {
    key: 'is_active',
    label: t('customer.groups.columns.active'),
    sortable: true,
    cell: 'active',
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('customer.groups.showActive') },
        { value: 'false', label: t('customer.groups.showInactive') },
      ],
    },
  },
]);

const actions = computed<DataTableAction<GroupRow>[]>(() => [
  ...(canConfigure.value ? [{ id: 'edit', label: t('customer.common.edit'), icon: 'ion:create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('customer.common.delete'), icon: 'ion:trash-outline', color: 'danger' }] : []),
]);

const formOpen = ref(false);
const editing = ref<GroupRow | null>(null);
const deleting = ref<{ id: string; name: string } | null>(null);

function edit(row: GroupRow | null): void {
  editing.value = row;
  formOpen.value = true;
}

function onAction(event: { actionId: string; row: GroupRow }): void {
  if (event.actionId === 'edit') edit(event.row);
  if (event.actionId === 'delete') deleting.value = { id: event.row.id, name: event.row.name };
}

function onSort(next: { sort: string; dir: SortDir }): void {
  list.setSort(next);
}
</script>

<template>
  <AppPage
    :title="$t('customer.groups.title')"
    content-layout="fill"
    :tabs="customerTabs($t)"
    :tabs-label="$t('customer.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="customer-groups-reconnecting"
    >
      {{ $t('customer.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="customer-groups-inactive"
      :heading="$t('customer.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="list.search.value"
      v-model:filters="filters"
      testid="customer-groups"
      fill
      server-side
      searchable
      filterable
      :row-clickable="canConfigure"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="list.page.value"
      :page-size="list.pageSize.value"
      :sort="list.sort.value"
      :sort-dir="list.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: GroupRow) => row.name"
      card-title-column="name"
      :card-icon="() => 'ion:people-outline'"
      :entity-label="{ one: $t('customer.groups.entity.one'), many: $t('customer.groups.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' ? error?.message : undefined"
      :addable="canConfigure"
      :actions="actions"
      :search-placeholder="$t('customer.groups.search')"
      :labels="{ add: $t('customer.common.add'), loadError: $t('customer.groups.loadError'), retry: $t('customer.live.retry') }"
      :columns="columns"
      @page-change="list.goToPage"
      @load-more="list.loadMore"
      @page-size-change="list.setPageSize"
      @sort-change="onSort"
      @row-click="edit"
      @action="onAction"
      @add="edit(null)"
      @retry="refresh()"
    >
      <template #active="{ row }">
        <span data-testid="customer-groups-active">{{ row.is_active ? $t('customer.common.yes') : $t('customer.common.no') }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="customer-groups-empty"
          icon="people-outline"
          :heading="list.filtered.value ? $t('customer.list.noResults') : $t('customer.groups.empty')"
          :message="list.filtered.value ? $t('customer.groups.noResults') : undefined"
        />
      </template>
    </DataTable>
    <GroupFormModal
      v-if="canConfigure"
      v-model:open="formOpen"
      :group="editing"
    />
    <EntityDeleteDialog
      v-if="canDelete"
      v-model:target="deleting"
      kind="groups"
    />
  </AppPage>
</template>
