<script setup lang="ts">
// Customers → Fields (WORKBOOK «Pantallas · Campos»; CUSTOMER-F29): the live `customer.field.list` in
// a server-side DataTable — Name, Type, Required, Order, Active —, by their order on the card,
// «Search field…» and filters behind the table's funnel by type, required and active. «Add», «Edit» (also a tap on the row) and
// «Delete» to whoever configures (deleting a field deletes its values on the cards).
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
import FieldFormModal from '../components/FieldFormModal.vue';
import { customerTabs } from '../lib/tabs';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import { type SortDir, useListState } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';
import type { CustomFieldType, FieldListIn, FieldRow } from '../operations';

const session = useSession();
// Whoever manages cards sees it too: without the permission, a manager approves it with their PIN (BASE-F84).
const canConfigure = computed(() => session.can('customer.configure') || session.can('customer.manage'));
const canDelete = canConfigure;
const { t } = useCustomerI18n();

const list = useListState({ sort: 'sort_order' });
const TYPES: CustomFieldType[] = ['text', 'number', 'date', 'boolean', 'select', 'textarea'];
/** The table's filters (its funnel): a filter not in use is absent; yes/no as `'true'`/`'false'`. */
const filters = ref<DataTableFilters>({});
watch(filters, (now) => list.restart({ narrowed: Object.keys(now).length > 0 }));
const query = computed(
  () =>
    ({
      ...(filters.value.field_type ? { field_type: filters.value.field_type as CustomFieldType } : {}),
      ...(filters.value.is_required ? { is_required: filters.value.is_required === 'true' } : {}),
      ...(filters.value.is_active ? { is_active: filters.value.is_active === 'true' } : {}),
      ...list.base.value,
    }) as FieldListIn,
);
const { data: result, status, error, refresh } = useLiveList('customer.field.list', () => query.value, list.windows);
list.followResult(result);
const inactive = computed(() => error.value?.code === 'app_inactive');

const columns = computed<DataTableColumn<FieldRow>[]>(() => [
  { key: 'name', label: t('customer.fields.columns.name'), sortable: true, priority: 'high' },
  {
    key: 'field_type',
    label: t('customer.fields.columns.type'),
    sortable: true,
    cell: 'type',
    filter: { type: 'select', options: TYPES.map((value) => ({ value, label: t(`customer.fieldType.${value}`) })) },
  },
  { key: 'is_required', label: t('customer.fields.columns.required'), sortable: true, cell: 'required', filter: { type: 'boolean' } },
  { key: 'sort_order', label: t('customer.fields.columns.order'), sortable: true, align: 'right', priority: 'low' },
  {
    key: 'is_active',
    label: t('customer.fields.columns.active'),
    sortable: true,
    cell: 'active',
    priority: 'low',
    filter: { type: 'boolean' },
  },
]);

const actions = computed<DataTableAction<FieldRow>[]>(() => [
  ...(canConfigure.value ? [{ id: 'edit', label: t('customer.common.edit'), icon: 'ion:create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('customer.common.delete'), icon: 'ion:trash-outline', color: 'danger' }] : []),
]);

const formOpen = ref(false);
const editing = ref<FieldRow | null>(null);
const deleting = ref<{ id: string; name: string } | null>(null);

function edit(row: FieldRow | null): void {
  editing.value = row;
  formOpen.value = true;
}

function onAction(event: { actionId: string; row: FieldRow }): void {
  if (event.actionId === 'edit') edit(event.row);
  if (event.actionId === 'delete') deleting.value = { id: event.row.id, name: event.row.name };
}

function onSort(next: { sort: string; dir: SortDir }): void {
  list.setSort(next);
}
</script>

<template>
  <AppPage
    :title="$t('customer.fields.title')"
    content-layout="fill"
    :tabs="customerTabs($t)"
    :tabs-label="$t('customer.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="customer-fields-reconnecting"
    >
      {{ $t('customer.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="customer-fields-inactive"
      :heading="$t('customer.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="list.search.value"
      v-model:filters="filters"
      testid="customer-fields"
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
      :card-title="(row: FieldRow) => row.name"
      card-title-column="name"
      :card-icon="() => 'ion:layers-outline'"
      :entity-label="{ one: $t('customer.fields.entity.one'), many: $t('customer.fields.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' ? error?.message : undefined"
      :addable="canConfigure"
      :actions="actions"
      :search-placeholder="$t('customer.fields.search')"
      :labels="{ add: $t('customer.common.add'), loadError: $t('customer.fields.loadError'), retry: $t('customer.live.retry') }"
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
      <template #type="{ row }">
        <span data-testid="customer-fields-type">{{ $t(`customer.fieldType.${row.field_type}`) }}</span>
      </template>
      <template #required="{ row }">
        <span data-testid="customer-fields-required">{{ row.is_required ? $t('customer.common.yes') : $t('customer.common.no') }}</span>
      </template>
      <template #active="{ row }">
        <span data-testid="customer-fields-active">{{ row.is_active ? $t('customer.common.yes') : $t('customer.common.no') }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="customer-fields-empty"
          icon="layers-outline"
          :heading="list.filtered.value ? $t('customer.list.noResults') : $t('customer.fields.empty')"
          :message="list.filtered.value ? $t('customer.fields.noResults') : undefined"
        />
      </template>
    </DataTable>
    <FieldFormModal
      v-if="canConfigure"
      v-model:open="formOpen"
      :field="editing"
    />
    <EntityDeleteDialog
      v-if="canDelete"
      v-model:target="deleting"
      kind="fields"
    />
  </AppPage>
</template>
