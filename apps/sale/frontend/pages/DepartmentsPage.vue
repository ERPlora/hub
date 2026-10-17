<script setup lang="ts">
// Sales & POS → Sections (SALE-F35; WORKBOOK «Pantallas · Secciones»): the old intro, then the live
// `sale.department.list` in a server-side DataTable — Name, «VAT charged» and Position —, «Search a
// section…», 50 a page sorted by position. «VAT charged» reads «Name · rate» with the rate the server
// says the category charges today (`tax_rate_pct`). Whoever may change the till settings gets «+», «Edit»
// (also a tap on the row) and «Delete» (confirmed with «Delete section»); anyone else sees the
// list read-only. Changes arrive through the stream (no refetch).
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState, useConfirm } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import DepartmentFormModal from '../components/backoffice/DepartmentFormModal.vue';
import ListNotices, { blockingError, type ListRefusal } from '../components/backoffice/ListNotices.vue';
import { refusal } from '../lib/refusal';
import { taxLabel } from '../lib/taxLabel';
import { useServerTable } from '../composables/useServerTable';
import { useTaxName } from '../composables/useTaxName';
import { useLocale, useT } from '../composables/useT';
import type { DepartmentOut } from '../operations';
import { saleTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('sale.manage_settings'));
const t = useT();
// What a section charges is named by the business territory's tax («VAT», «IGIC», «IPSI»).
const taxName = useTaxName();
const locale = useLocale();
const { confirm } = useConfirm();

// `search` of DepartmentListIn takes 60 characters.
const table = useServerTable('sale.department.list', { sort: 'sort_order', maxSearch: 60 });
const { data: result, status, error } = table;

const blocked = computed(() => blockingError(error.value));
const tableError = computed(() => (status.value === 'error' ? error.value?.message : undefined));

const columns = computed<DataTableColumn<DepartmentOut>[]>(() => [
  { key: 'name', label: t('sale.departments.columns.name'), sortable: true, priority: 'high' },
  {
    key: 'tax_category_key',
    label: t('sale.departments.columns.taxCategory', { tax: taxName.value }),
    format: (_, row) => taxLabel(row.tax_category_name, row.tax_rate_pct, locale.value, row.tax_category_key),
  },
  { key: 'sort_order', label: t('sale.departments.columns.sortOrder'), sortable: true, align: 'right' },
]);

// ── Add, edit, delete ─────────────────────────────────────────────────────────────────────────────
const formOpen = ref(false);
const editing = ref<DepartmentOut | null>(null);
const removal = useCommand('sale.department.delete');
const removing = ref<string | null>(null);
const refused = ref<ListRefusal | null>(null);

const actions = computed<DataTableAction<DepartmentOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('sale.departments.edit'), icon: 'ion:create-outline' },
        { id: 'delete', label: t('sale.departments.delete'), icon: 'ion:trash-outline', color: 'danger', loading: (row) => removing.value === row.id },
      ]
    : [],
);

function edit(department: DepartmentOut | null): void {
  if (!canManage.value) return;
  refused.value = null;
  editing.value = department;
  formOpen.value = true;
}

async function remove(department: DepartmentOut): Promise<void> {
  refused.value = null;
  const yes = await confirm({
    title: t('sale.departments.deleteTitle'),
    message: t('sale.departments.deleteMessage', { name: department.name, tax: taxName.value }),
    confirmLabel: t('sale.departments.delete'),
    cancelLabel: t('sale.departments.deleteCancel'),
    confirmIcon: 'ion:trash-outline',
    tone: 'danger',
  });
  if (!yes) return;
  removing.value = department.id;
  try {
    await removal.run({ id: department.id });
  } catch {
    refused.value = { heading: t('sale.departments.deleteFailed'), message: refusal(removal.error.value, '')?.message };
  } finally {
    removing.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: DepartmentOut }): void {
  // The server checks the permission on every command; the page does not offer what it would refuse.
  if (!canManage.value) return;
  if (actionId === 'edit') edit(row);
  else if (actionId === 'delete') void remove(row);
}

const cardTitle = (row: DepartmentOut): string => row.name;
</script>

<template>
  <AppPage
    :title="$t('sale.title')"
    content-layout="fill"
    :tabs="saleTabs($t)"
    :tabs-label="$t('sale.tabs.label')"
  >
    <p
      class="sale-backoffice-intro"
      data-testid="sale-departments-intro"
    >
      {{ $t('sale.departments.intro', { tax: taxName }) }}
    </p>
    <ListNotices
      testid="sale-departments"
      :status="status"
      :error="error"
      :refused="refused"
    />
    <DataTable
      v-if="!blocked"
      v-model:search="table.search.value"
      testid="sale-departments"
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
      :entity-label="{ one: $t('sale.departments.entity.one'), many: $t('sale.departments.entity.many') }"
      :loading="status === 'loading'"
      :error="tableError"
      :addable="canManage"
      :row-clickable="canManage"
      :actions="actions"
      :search-placeholder="$t('sale.departments.search')"
      :labels="{
        add: $t('sale.departments.add'),
        loading: $t('sale.departments.loading'),
        loadError: $t('sale.departments.loadError'),
        retry: $t('sale.live.retry'),
      }"
      :columns="columns"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @add="edit(null)"
      @row-click="edit"
      @action="onAction"
      @retry="table.refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="sale-departments-empty"
          icon="grid-outline"
          :heading="table.filtered.value ? $t('sale.departments.noResults') : $t('sale.departments.empty')"
          :message="table.filtered.value ? $t('sale.departments.noResultsMessage') : undefined"
        />
      </template>
    </DataTable>
    <DepartmentFormModal
      v-if="canManage"
      v-model:open="formOpen"
      :department="editing"
    />
  </AppPage>
</template>

<style scoped>
.sale-backoffice-intro {
  margin: 0 0 12px;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
