<script setup lang="ts">
// Inventory → Categories (WORKBOOK «Categorías», INVENTORY-F06/F07/F10/F11), the old
// `erp-inventory-categories`: the live `inventory.category.list` in a server-side DataTable — Name,
// Slug and Products (active ones) —, 25 a page by name. «+», a row or «Edit» open the form
// (CategoryFormModal); «Delete» says what will happen and unlinks; import (calls of at most 100 rows,
// then «Import result») and export (the server's file, filtered as the list). Writes come back
// through the stream: nothing here refetches.
import { type DataTableAction, type DataTableActionEvent, type DataTableColumn, DataTable, EmptyState, InlineFeedback, useConfirm } from '@erplora/ui/components';
import { type InputOf, type OutputOf, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { computed, ref } from 'vue';

import CategoryFormModal from '../components/CategoryFormModal.vue';
import CsvButtons from '../components/CsvButtons.vue';
import ImportReportModal from '../components/ImportReportModal.vue';
import { useInventoryTabs } from '../composables/useInventoryTabs';
import { useLiveList } from '../composables/useLiveList';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { parseCsv } from '../lib/csv';
import { saveTextFile } from '../lib/download';
import { CATEGORY_IMPORT_ALIASES, guessMapping, mapRow } from '../lib/import-mapping';
import { addReport, chunk, emptyReport, failRows, type ImportReport } from '../lib/import-report';

type Category = OutputOf<'inventory.category.list'>['rows'][number];

const { t } = useT();
const tabs = useInventoryTabs();
const session = useSession();
const client = useLiveClient();
const { confirm } = useConfirm();

const canAdd = computed(() => session.can('inventory.add_category'));
const canChange = computed(() => session.can('inventory.change_category'));
const canDelete = computed(() => session.can('inventory.delete_category'));
const canExport = computed(() => session.can('inventory.export_product'));

const table = useServerTable<NonNullable<InputOf<'inventory.category.list'>['sort']>>({ sort: 'name', pageSize: 25 });
const { data: result, status, error, refresh } = useLiveList('inventory.category.list', () => table.params.value, table.windows);
table.followResult(result);

const inactive = computed(() => error.value?.code === 'app_inactive');
/** A refused row action or import: no dialog is open, so it is said above the table. */
const pageError = ref('');

const editing = ref<Category | null>(null);
const formOpen = ref(false);

function openForm(row: Category | null): void {
  editing.value = row;
  formOpen.value = true;
}

const remove = useCommand('inventory.category.delete');

async function askDelete(row: Category): Promise<void> {
  const yes = await confirm({
    title: t('inventory.categories.delete.title'),
    message: t('inventory.categories.delete.message', { name: row.name, n: row.product_count }),
    confirmLabel: t('inventory.categories.delete.confirm'),
    tone: 'danger',
  });
  if (!yes) return;
  pageError.value = '';
  try {
    await remove.run({ id: row.id });
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : t('inventory.categories.delete.error');
  }
}

function onAction(event: DataTableActionEvent<Category>): void {
  if (event.actionId === 'edit') openForm(event.row);
  else if (event.actionId === 'delete') void askDelete(event.row);
}

const actions = computed<DataTableAction<Category>[]>(() => [
  ...(canChange.value ? [{ id: 'edit', label: t('inventory.products.actions.edit'), icon: 'ion:create-outline' }] : []),
  ...(canDelete.value ? [{ id: 'delete', label: t('inventory.products.actions.delete'), icon: 'ion:trash-outline', color: 'danger' }] : []),
]);

const columns = computed<DataTableColumn<Category>[]>(() => [
  { key: 'name', label: t('inventory.categories.columns.name'), sortable: true, priority: 'high' },
  { key: 'slug', label: t('inventory.categories.columns.slug'), sortable: true },
  { key: 'product_count', label: t('inventory.categories.columns.products'), sortable: true, align: 'right' },
]);

// ── Import and export (INVENTORY-F10, F11) ───────────────────────────────────────────────────────
const busy = ref(false);
const report = ref<ImportReport | null>(null);
const reportOpen = ref(false);

async function importFile(text: string): Promise<void> {
  pageError.value = '';
  const { headers, rows } = parseCsv(text);
  if (rows.length === 0) {
    pageError.value = t('inventory.import.emptyFile');
    return;
  }
  const mapping = guessMapping(headers, CATEGORY_IMPORT_ALIASES);
  const mapped = rows.map((row) => ({ name: '', slug: '', tax_category_key: '', ...mapRow(row.values, mapping), line: row.line }));
  busy.value = true;
  let done = emptyReport();
  try {
    for (const part of chunk(mapped)) {
      try {
        done = addReport(done, await client.api.call('inventory.category.bulk_create', { rows: part }));
      } catch (failure) {
        const reason = t('inventory.import.chunkFailed', { reason: failure instanceof Error ? failure.message : String(failure) });
        done = failRows(done, part.map((row) => ({ line: row.line, key: row.name, reason })));
      }
    }
  } finally {
    busy.value = false;
  }
  report.value = done;
  reportOpen.value = true;
}

async function exportFile(): Promise<void> {
  pageError.value = '';
  busy.value = true;
  try {
    const { search, sort } = table.params.value;
    const file = await client.api.call('inventory.category.export', { search, sort });
    saveTextFile(file.filename, file.content, file.content_type);
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : String(failure);
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <AppPage
    :title="$t('inventory.title')"
    content-layout="fill"
    :tabs="tabs"
    :tabs-label="$t('inventory.tabs.label')"
  >
    <InlineFeedback
      v-if="status === 'reconnecting'"
      tone="warning"
      data-testid="inventory-categories-reconnecting"
    >
      {{ $t('inventory.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="inventory-categories-page-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="inventory-categories-inactive"
      :heading="$t('inventory.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="table.search.value"
      testid="inventory-categories"
      fill
      server-side
      searchable
      :row-clickable="canChange"
      :rows="result?.rows ?? []"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sortKey.value"
      :sort-dir="table.sortDir.value"
      :views="['table', 'cards']"
      :card-title="(row: Category) => row.name"
      :columns="columns"
      :actions="actions"
      :addable="canAdd"
      :loading="status === 'loading'"
      :error="status === 'error' ? error?.message : undefined"
      :search-placeholder="$t('inventory.categories.search')"
      :labels="{ add: $t('inventory.categories.new'), loadError: $t('inventory.categories.loadError'), retry: $t('inventory.live.retry') }"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="canChange && openForm($event)"
      @action="onAction"
      @add="openForm(null)"
      @retry="refresh()"
    >
      <template #toolbar>
        <CsvButtons
          testid="inventory-categories"
          :importable="canAdd"
          :exportable="canExport"
          :busy="busy"
          @import="importFile"
          @export="exportFile"
          @read-error="pageError = $t('inventory.import.readError')"
        />
      </template>
      <template #empty>
        <EmptyState
          data-testid="inventory-categories-empty"
          icon="file-tray-outline"
          :heading="table.filtered.value ? $t('inventory.categories.noResults') : $t('inventory.categories.empty')"
        />
      </template>
    </DataTable>
    <CategoryFormModal
      v-if="canAdd || canChange"
      v-model:open="formOpen"
      :category="editing"
    />
    <ImportReportModal
      v-model:open="reportOpen"
      :report="report"
    />
  </AppPage>
</template>
