<script setup lang="ts">
// Customers → Tags (WORKBOOK «Pantallas · Etiquetas»; CUSTOMER-F28): the live `customer.tag.list` in
// a server-side DataTable — Name, Color, Customers (live cards with it), Active —, «Search tag…» and
// the active filter behind the table's funnel. «Add» and «Edit» (also a tap on the row) to whoever configures; «Delete» to the
// owner and the admin. The same screen as Groups.
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
import TagFormModal from '../components/TagFormModal.vue';
import { customerTabs } from '../lib/tabs';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import { type SortDir, useListState } from '../lib/useListState';
import { useLiveList } from '../lib/useLiveList';
import { isThemeColor } from '../lib/colors';
import type { TagListIn, TagRow } from '../operations';

const session = useSession();
const canConfigure = computed(() => session.can('customer.configure'));
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
    }) as TagListIn,
);
const { data: result, status, error, refresh } = useLiveList('customer.tag.list', () => query.value, list.windows);
list.followResult(result);
const inactive = computed(() => error.value?.code === 'app_inactive');

const columns = computed<DataTableColumn<TagRow>[]>(() => [
  { key: 'name', label: t('customer.tags.columns.name'), sortable: true, priority: 'high' },
  { key: 'color', label: t('customer.tags.columns.color'), sortable: true, cell: 'color' },
  { key: 'customer_count', label: t('customer.tags.columns.customers'), sortable: true, align: 'right' },
  {
    key: 'is_active',
    label: t('customer.tags.columns.active'),
    sortable: true,
    cell: 'active',
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('customer.tags.showActive') },
        { value: 'false', label: t('customer.tags.showInactive') },
      ],
    },
  },
]);

const actions = computed<DataTableAction<TagRow>[]>(() => [
  ...(canConfigure.value ? [{ id: 'edit', label: t('customer.common.edit'), icon: 'ion:create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('customer.common.delete'), icon: 'ion:trash-outline', color: 'danger' }] : []),
]);

const formOpen = ref(false);
const editing = ref<TagRow | null>(null);
const deleting = ref<{ id: string; name: string } | null>(null);

function edit(row: TagRow | null): void {
  editing.value = row;
  formOpen.value = true;
}

function onAction(event: { actionId: string; row: TagRow }): void {
  if (event.actionId === 'edit') edit(event.row);
  if (event.actionId === 'delete') deleting.value = { id: event.row.id, name: event.row.name };
}

function onSort(next: { sort: string; dir: SortDir }): void {
  list.setSort(next);
}
</script>

<template>
  <AppPage
    :title="$t('customer.tags.title')"
    content-layout="fill"
    :tabs="customerTabs($t)"
    :tabs-label="$t('customer.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="customer-tags-reconnecting"
    >
      {{ $t('customer.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="customer-tags-inactive"
      :heading="$t('customer.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="list.search.value"
      v-model:filters="filters"
      testid="customer-tags"
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
      :card-title="(row: TagRow) => row.name"
      :card-icon="() => 'ion:list-outline'"
      :entity-label="{ one: $t('customer.tags.entity.one'), many: $t('customer.tags.entity.many') }"
      :loading="status === 'loading'"
      :error="status === 'error' ? error?.message : undefined"
      :addable="canConfigure"
      :actions="actions"
      :search-placeholder="$t('customer.tags.search')"
      :labels="{ add: $t('customer.common.add'), loadError: $t('customer.tags.loadError'), retry: $t('customer.live.retry') }"
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
      <template #color="{ row }">
        <span
          class="customer-color"
          data-testid="customer-tags-color"
        >
          <span
            class="customer-color__dot"
            :class="isThemeColor(row.color) ? `customer-color__dot--${row.color}` : undefined"
            aria-hidden="true"
          />
          {{ isThemeColor(row.color) ? $t(`customer.colors.${row.color}`) : row.color }}
        </span>
      </template>
      <template #active="{ row }">
        <span data-testid="customer-tags-active">{{ row.is_active ? $t('customer.common.yes') : $t('customer.common.no') }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="customer-tags-empty"
          icon="list-outline"
          :heading="list.filtered.value ? $t('customer.list.noResults') : $t('customer.tags.empty')"
          :message="list.filtered.value ? $t('customer.tags.noResults') : undefined"
        />
      </template>
    </DataTable>
    <TagFormModal
      v-if="canConfigure"
      v-model:open="formOpen"
      :tag="editing"
    />
    <EntityDeleteDialog
      v-if="canDelete"
      v-model:target="deleting"
      kind="tags"
    />
  </AppPage>
</template>

<style scoped>
.customer-color {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}

.customer-color__dot {
  width: 0.75rem;
  height: 0.75rem;
  border-radius: 50%;
  background: var(--ion-color-medium);
  flex: none;
}

.customer-color__dot--primary { background: var(--ion-color-primary); }
.customer-color__dot--secondary { background: var(--ion-color-secondary); }
.customer-color__dot--tertiary { background: var(--ion-color-tertiary); }
.customer-color__dot--success { background: var(--ion-color-success); }
.customer-color__dot--warning { background: var(--ion-color-warning); }
.customer-color__dot--danger { background: var(--ion-color-danger); }
.customer-color__dot--medium { background: var(--ion-color-medium); }
.customer-color__dot--dark { background: var(--ion-color-dark); }
</style>
