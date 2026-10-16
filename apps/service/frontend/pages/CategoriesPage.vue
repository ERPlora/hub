<script setup lang="ts">
// Services → Categories (WORKBOOK «Pantallas · Categorías»; SERVICE-F07, F08): the live
// `service.category.list` in a server-side DataTable — Name, Parent category, Order and Services (the
// offered ones in it) —, «Search category…», by order then name, 50 a page. «New category» (whoever
// may add) and a row or its Edit (whoever may edit) open the form; Delete (owner and admin) asks
// first, with how many services will be left without a category. Changes come back through the stream.
import { ConfirmDialog, DataTable, type DataTableAction, type DataTableColumn, EmptyState } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import CategoryFormModal from '../components/CategoryFormModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import type { CategoryOut } from '../operations';
import { serviceTabs } from '../tabs';

const session = useSession();
const t = useT();
const canAdd = computed(() => session.can('service.add_category'));
const canChange = computed(() => session.can('service.change_category'));
const canDelete = computed(() => session.can('service.delete_category'));

const table = useServerTable({ sort: 'sort_order' });
const { data: result, status, error, refresh } = useLiveList('service.category.list', () => table.query.value, () => table.windows.value);
table.followResult(result);
const blocked = computed(() => blockingError(error.value));

const columns = computed<DataTableColumn<CategoryOut>[]>(() => [
  { key: 'name', label: t('service.categories.columns.name'), sortable: true, priority: 'high' },
  { key: 'parent_name', label: t('service.categories.columns.parent'), sortable: true, format: (_, row) => row.parent_name ?? t('service.none') },
  { key: 'sort_order', label: t('service.categories.columns.order'), sortable: true, align: 'right', format: (_, row) => String(row.sort_order) },
  {
    key: 'service_count',
    label: t('service.categories.columns.services'),
    sortable: true,
    align: 'right',
    format: (_, row) => String(row.service_count),
  },
]);

const actions = computed<DataTableAction<CategoryOut>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('service.categories.actions.edit'), icon: 'create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('service.categories.actions.delete'), icon: 'trash-outline', color: 'danger' }] : []),
]);

const editing = ref<CategoryOut | null>(null);
const formOpen = ref(false);
function openForm(category: CategoryOut | null): void {
  editing.value = category;
  formOpen.value = true;
}

const remove = useCommand('service.category.delete');
const deleting = ref<CategoryOut | null>(null);
const deleteOpen = ref(false);
const consequences = computed(() =>
  deleting.value && deleting.value.service_count > 0 ? [t('service.categories.delete.impact', { count: deleting.value.service_count })] : [],
);

async function confirmDelete(): Promise<void> {
  if (!deleting.value) return;
  try {
    await remove.run({ id: deleting.value.id });
  } catch {
    return; // The dialog says why.
  }
  deleteOpen.value = false;
}

function onAction({ actionId, row }: { actionId: string; row: CategoryOut }): void {
  if (actionId === 'edit') openForm(row);
  if (actionId === 'delete') {
    remove.error.value = null;
    deleting.value = row;
    deleteOpen.value = true;
  }
}
</script>

<template>
  <AppPage
    :title="$t('service.title')"
    content-layout="fill"
    :tabs="serviceTabs($t, { settings: session.can('service.manage_settings') })"
    :tabs-label="$t('service.tabs.label')"
  >
    <PageNotices
      testid="service-categories"
      :status="status"
      :error="error"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="service-categories"
      fill
      server-side
      searchable
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="(row: CategoryOut) => row.name"
      :card-icon="() => 'pricetags-outline'"
      :entity-label="{ one: $t('service.categories.entity.one'), many: $t('service.categories.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' && !blocked ? $t('service.categories.loadError') : undefined"
      :addable="canAdd"
      :row-clickable="canChange"
      :actions="actions"
      :search-placeholder="$t('service.categories.search')"
      :labels="{ add: $t('service.categories.new'), loadError: $t('service.categories.loadError'), retry: $t('service.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="(row: CategoryOut) => canChange && openForm(row)"
      @add="openForm(null)"
      @action="onAction"
      @retry="refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="service-categories-empty"
          icon="pricetags-outline"
          :heading="table.filtered.value ? $t('service.noResults') : $t('service.categories.empty')"
          :message="table.filtered.value ? $t('service.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <CategoryFormModal
      v-model:open="formOpen"
      :category="editing"
    />
    <ConfirmDialog
      v-model:open="deleteOpen"
      testid="service-categories-delete"
      tone="danger"
      :title="t('service.categories.delete.title')"
      :message="deleting ? t('service.categories.delete.message', { name: deleting.name }) : ''"
      :consequences="consequences"
      :confirm-label="t('service.categories.delete.confirm')"
      :cancel-label="t('service.cancel')"
      :pending="remove.pending.value"
      :error="remove.error.value"
      @confirm="confirmDelete"
      @cancel="deleteOpen = false"
    />
  </AppPage>
</template>
