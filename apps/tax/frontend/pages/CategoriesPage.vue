<script setup lang="ts">
// Taxes → Categories (TAX-F01, F02): the live `tax.category.list` in a server-side DataTable — Key,
// Name, Description, Origin («System» or «Custom»), Active and the rate in force today in the
// business's country —, search, column filters behind the table's funnel, sort by any column, 50 a page sorted by key. «+» opens
// «New tax category» for whoever can manage; the new row arrives through the stream (no refetch).
import { type DataTableColumn, type DataTableFilters, DataTable, EmptyState } from '@erplora/ui/components';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { computed, ref, watch } from 'vue';

import CategoryCreateModal from '../components/CategoryCreateModal.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import SetupNotice from '../components/SetupNotice.vue';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useLocale, useT } from '../composables/useT';
import { formatPercent } from '../lib/format';
import { categoryDisplayName, chargesNoTax } from '../lib/rules';
import type { CategoryListIn, CategoryRowOut } from '../operations';
import { taxTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('tax.manage'));
const t = useT();
const locale = useLocale();

const table = useServerTable({ sort: 'key' });
/** The table's filters (its funnel): a filter not in use is absent. */
const filters = ref<DataTableFilters>({});
watch(filters, (now) => table.restart({ narrowed: Object.keys(now).length > 0 }));

/** The filters as the query takes them: Origin is a yes/no. */
function filterParams(values: DataTableFilters): Partial<CategoryListIn> {
  const { is_system: origin, ...text } = values;
  return { ...text, ...(origin ? { is_system: origin === 'true' } : {}) };
}

const {
  data: result,
  status,
  error,
  refresh,
} = useLiveList('tax.category.list', () => ({ ...filterParams(filters.value), ...table.query.value }) as CategoryListIn, () => table.windows.value);
table.followResult(result);

const blocked = computed(() => blockingError(error.value));
/** A filter the server refused (a 422 of the list): said under the filter, the rows stay. */
const filterErrors = computed(() => error.value?.fields ?? {});
const tableError = computed(() => (status.value === 'error' && !Object.keys(filterErrors.value).length ? error.value?.message : undefined));
const creating = ref(false);

/** «21.00%» («21,00 %») in force today; a class without tax says its class; no rule, «—». */
function rateToday(row: CategoryRowOut): string {
  if (row.rate_pct === null) return '—';
  return chargesNoTax(row.operation_class) ? t(`tax.classes.${row.operation_class}`) : formatPercent(row.rate_pct, locale.value);
}

const columns = computed<DataTableColumn<CategoryRowOut>[]>(() => [
  // Each text filter as long as CategoryListIn takes it.
  { key: 'key', label: t('tax.categories.columns.key'), sortable: true, priority: 'high', filter: { type: 'text', maxlength: 80 } },
  {
    key: 'display_name',
    label: t('tax.categories.columns.name'),
    sortable: true,
    format: (_, row) => categoryDisplayName(row),
    filter: { type: 'text', maxlength: 255 },
  },
  {
    key: 'display_description',
    label: t('tax.categories.columns.description'),
    sortable: true,
    priority: 'low',
    format: (_, row) => row.display_description.trim() || row.description.trim() || '—',
    filter: { type: 'text', maxlength: 1000 },
  },
  {
    key: 'is_system',
    label: t('tax.categories.columns.origin'),
    sortable: true,
    cell: 'origin',
    filter: {
      type: 'select',
      options: [
        { value: 'true', label: t('tax.categories.origin.system') },
        { value: 'false', label: t('tax.categories.origin.custom') },
      ],
    },
  },
  {
    key: 'is_active',
    label: t('tax.categories.columns.active'),
    sortable: true,
    priority: 'low',
    format: (value) => (value ? t('tax.yes') : t('tax.no')),
  },
  { key: 'rate_pct', label: t('tax.categories.columns.rate'), align: 'right', format: (_, row) => rateToday(row) },
]);
</script>

<template>
  <AppPage
    :title="$t('tax.title')"
    content-layout="fill"
    :tabs="taxTabs($t)"
    :tabs-label="$t('tax.tabs.label')"
  >
    <PageNotices
      testid="tax-categories"
      :status="status"
      :error="error"
      :read-only="!canManage"
    />
    <SetupNotice v-if="canManage" />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="tax-categories"
      fill
      server-side
      searchable
      filterable
      :filter-errors="filterErrors"
      row-key="key"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sort.value"
      :sort-dir="table.dir.value"
      :views="['table', 'cards']"
      :card-title="categoryDisplayName"
      :entity-label="{ one: $t('tax.categories.entity.one'), many: $t('tax.categories.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canManage"
      :search-placeholder="$t('tax.categories.search')"
      :labels="{ add: $t('tax.add'), loadError: $t('tax.categories.loadError'), retry: $t('tax.live.retry') }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="creating = true"
      @retry="refresh()"
    >
      <template #origin="{ row }">
        <span
          v-if="row.is_system"
          class="tax-origin"
          data-testid="tax-category-system"
        >
          <HubIcon name="ion:lock-closed-outline" />
          {{ $t('tax.categories.origin.system') }}
        </span>
        <span
          v-else
          data-testid="tax-category-custom"
        >{{ $t('tax.categories.origin.custom') }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="tax-categories-empty"
          icon="pricetags-outline"
          :heading="table.filtered.value ? $t('tax.noResults') : $t('tax.categories.empty')"
          :message="table.filtered.value ? $t('tax.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <CategoryCreateModal
      v-if="canManage"
      v-model:open="creating"
    />
  </AppPage>
</template>

<style scoped>
.tax-origin {
  display: inline-flex;
  align-items: center;
  gap: 0.3rem;
}
</style>
