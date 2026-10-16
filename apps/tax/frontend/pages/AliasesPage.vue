<script setup lang="ts">
// Taxes → Aliases (TAX-F13, F14): the live `tax.alias.list` in a server-side DataTable — Alias,
// Category, Origin («Shipped» or «Learned») and Active —, search, column filters (Alias, Category,
// Origin) and sort by any column, 50 a page sorted by alias. «+» opens «New category alias» for whoever
// can manage; the new row arrives through the stream.
import { type DataTableColumn, DataTable, EmptyState } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import AliasCreateModal from '../components/AliasCreateModal.vue';
import FilterPanel, { type FilterSpec, type FilterValues } from '../components/FilterPanel.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { categoryOptionLabel } from '../lib/rules';
import type { AliasListIn, AliasOut, AliasSource } from '../operations';
import { taxTabs } from '../tabs';

const SOURCES: readonly AliasSource[] = ['shipped', 'learned'];

const session = useSession();
const canManage = computed(() => session.can('tax.manage'));
const t = useT();

const table = useServerTable({ sort: 'alias' });
const filters = ref<FilterValues>({});
watch(filters, (now) => table.restart({ narrowed: Object.keys(now).length > 0 }));

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList('tax.alias.list', () => ({ ...filters.value, ...table.query.value }) as AliasListIn, () => table.windows.value);
table.followResult(result);

/** The Category filter searches the server: all the business's categories, not a first page. */
const categoryQuery = ref('');
const { data: categories } = useLive('tax.category.list', () => ({
  search: categoryQuery.value || undefined,
  sort: 'display_name' as const,
  dir: 'asc' as const,
  limit: 50,
}));

const blocked = computed(() => blockingError(error.value));
/** A filter the server refused (a 422 of the list): said under the filter, the rows stay. */
const filterErrors = computed(() => error.value?.fields ?? {});
const tableError = computed(() => (status.value === 'error' && !Object.keys(filterErrors.value).length ? error.value?.message : undefined));
const creating = ref(false);

const filterSpecs = computed<FilterSpec[]>(() => [
  // As long as AliasListIn takes it.
  { kind: 'text', key: 'alias', label: t('tax.aliases.columns.alias'), maxlength: 200 },
  {
    kind: 'search',
    key: 'tax_category_key',
    label: t('tax.aliases.columns.category'),
    options: (categories.value?.rows ?? []).map((category) => ({ value: category.key, label: categoryOptionLabel(category) })),
    search: (text: string) => (categoryQuery.value = text),
  },
  {
    kind: 'select',
    key: 'source',
    label: t('tax.aliases.columns.source'),
    options: SOURCES.map((value) => ({ value, label: t(`tax.aliases.source.${value}`) })),
  },
]);

const columns = computed<DataTableColumn<AliasOut>[]>(() => [
  { key: 'alias', label: t('tax.aliases.columns.alias'), sortable: true, priority: 'high' },
  { key: 'tax_category_key', label: t('tax.aliases.columns.category'), sortable: true },
  { key: 'source', label: t('tax.aliases.columns.source'), sortable: true, format: (_, row) => t(`tax.aliases.source.${row.source}`) },
  {
    key: 'is_active',
    label: t('tax.aliases.columns.active'),
    sortable: true,
    priority: 'low',
    format: (value) => (value ? t('tax.yes') : t('tax.no')),
  },
]);

const cardTitle = (row: AliasOut): string => row.alias;
</script>

<template>
  <AppPage
    :title="$t('tax.title')"
    content-layout="fill"
    :tabs="taxTabs($t)"
    :tabs-label="$t('tax.tabs.label')"
  >
    <PageNotices
      testid="tax-aliases"
      :status="status"
      :error="error"
      :read-only="!canManage"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="tax-aliases"
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
      :card-title="cardTitle"
      :entity-label="{ one: $t('tax.aliases.entity.one'), many: $t('tax.aliases.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canManage"
      :search-placeholder="$t('tax.aliases.search')"
      :labels="{ add: $t('tax.add'), loadError: $t('tax.aliases.loadError'), retry: $t('tax.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="creating = true"
      @retry="refresh()"
    >
      <template #filters>
        <FilterPanel
          v-model="filters"
          testid="tax-aliases"
          :filters="filterSpecs"
          :field-errors="filterErrors"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="tax-aliases-empty"
          icon="swap-vertical-outline"
          :heading="table.filtered.value ? $t('tax.noResults') : $t('tax.aliases.empty')"
          :message="table.filtered.value ? $t('tax.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <AliasCreateModal
      v-if="canManage"
      v-model:open="creating"
    />
  </AppPage>
</template>
