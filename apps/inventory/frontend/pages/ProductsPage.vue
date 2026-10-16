<script setup lang="ts">
// Inventory → Products (WORKBOOK «Productos», INVENTORY-F01–F05, F08, F09, F11, F13–F15, F20), the old
// `erp-inventory-products`: the live `inventory.product.list` in a server-side DataTable — Name, SKU,
// Price, Stock («—» without stock control) and Status (a switch, «Yes»/«No», or «Not configured ·
// Missing tax category», which opens the form) —, search, sort, the filters behind the table's funnel
// (name, SKU, price and stock ranges, status; the old table's), 50 a page. «+», import and
// export CSV; per row the sheet, the stock dialogs (physical products), edit and delete; each only for
// whoever may. Writes come back through the stream; nothing here refetches. A refused row action (the
// switch, delete, export) is said above the table: no dialog is open then.
import {
  type DataTableAction,
  type DataTableActionEvent,
  type DataTableColumn,
  type DataTableFilters,
  DataTable,
  EmptyState,
  InlineFeedback,
  useConfirm,
} from '@erplora/ui/components';
import { type InputOf, type OutputOf, useCommand, useLiveClient } from '@erplora/ui/sdk';
import { AppPage, useSession } from '@erplora/ui/shell';
import { IonButton, IonChip, IonLabel, IonProgressBar, IonToggle } from '@ionic/vue';
import { HubIcon } from '@erplora/ui/shell';
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import CsvButtons from '../components/CsvButtons.vue';
import ImportPreviewModal from '../components/ImportPreviewModal.vue';
import ImportReportModal from '../components/ImportReportModal.vue';
import ImportTaxModal from '../components/ImportTaxModal.vue';
import ProductDetailModal from '../components/ProductDetailModal.vue';
import ProductFormModal from '../components/ProductFormModal.vue';
import StockModal, { type StockAction } from '../components/StockModal.vue';
import { useInventoryTabs } from '../composables/useInventoryTabs';
import { useLiveList } from '../composables/useLiveList';
import { useProductImport } from '../composables/useProductImport';
import { useServerTable } from '../composables/useServerTable';
import { useT } from '../composables/useT';
import { useUnits } from '../composables/useUnits';
import { saveTextFile } from '../lib/download';
import { formatMoney, formatQuantity } from '../lib/format';
import { filterParams, filtersInUse, PRODUCT_STATUSES, type ProductStatus, type UnreadableEnd, unreadableEnds } from '../lib/productFilters';

type Product = OutputOf<'inventory.product.list'>['rows'][number];
/** `?status=` of a link (the till's «N articles cannot be sold» opens «unconfigured»). */
const STATUS_FROM_QUERY: Record<string, ProductStatus> = { unconfigured: 'needs_tax_setup', needs_tax_setup: 'needs_tax_setup', active: 'active', inactive: 'inactive' };

const { t, locale } = useT();
const tabs = useInventoryTabs();
const session = useSession();
const client = useLiveClient();
const route = useRoute();
const { confirm } = useConfirm();
const { units } = useUnits();

const can = (permission: string) => computed(() => session.can(permission));
const canAdd = can('inventory.add_product');
const canChange = can('inventory.change_product');
const canDelete = can('inventory.delete_product');
const canMove = can('inventory.adjust_stock');
const canImport = computed(() => session.can('inventory.import_product') && session.can('inventory.add_product'));
const canExport = can('inventory.export_product');

// ── The list ──────────────────────────────────────────────────────────────────────────────────────
const table = useServerTable<NonNullable<InputOf<'inventory.product.list'>['sort']>>({ sort: 'name' });
const PATH = '/inventory/products';
/** The filters with the Status of a link's `?status=` (none: no Status filter); the others stay. */
function withStatusOf(values: DataTableFilters, query: unknown): DataTableFilters {
  const rest = Object.fromEntries(Object.entries(values).filter(([name]) => name !== 'status'));
  const status = STATUS_FROM_QUERY[String(query ?? '')];
  return status ? { ...rest, status } : rest;
}
/** The table's filters (its funnel), as typed: the price in euros. A filter not in use is absent. */
const filters = ref<DataTableFilters>(withStatusOf({}, route.query.status));
// A link to this page with another `?status=` while it is open (Ionic keeps it mounted) applies it.
// Only on this page's own address: leaving for another tab leaves the filter as it was.
watch(
  () => [route.path, route.query.status] as const,
  ([path, query], [, before]) => {
    if (path === PATH && query !== before) filters.value = withStatusOf(filters.value, query);
  },
);
// Only the filters that really apply narrow the list (an amount it cannot read does not).
table.restart({ narrowed: filtersInUse(filters.value) > 0 });
watch(filters, (now) => table.restart({ narrowed: filtersInUse(now) > 0 }));

const listFilters = () => filterParams(filters.value);
const { data: result, status: listStatus, error, refresh } = useLiveList(
  'inventory.product.list',
  () => ({ ...listFilters(), ...table.params.value }),
  table.windows,
);
table.followResult(result);
const rows = computed(() => result.value?.rows ?? []);
const inactive = computed(() => error.value?.code === 'app_inactive');

/** Why an end of a range cannot be read, as its field would say it. */
function unreadableMessage({ name, problem }: UnreadableEnd): string {
  if (problem === 'not_quantity') return t('inventory.common.noQuantity');
  if (problem.reason === 'not_amount') return t('inventory.common.noAmount');
  return t('inventory.common.ambiguousAmount', {
    typed: (filters.value[name] ?? '').trim(),
    grouped: formatMoney(problem.grouped, locale.value),
    decimal: formatMoney(problem.decimal, locale.value),
  });
}
/** Under each filter: an end it cannot read, else what the server refused (a 422 of the list). */
const filterErrors = computed<Record<string, string>>(() => ({
  ...(error.value?.fields ?? {}),
  ...Object.fromEntries(unreadableEnds(filters.value).map((end) => [end.name, unreadableMessage(end)])),
}));
/** A refused filter is said under it and the rows stay; any other failure replaces them. */
const tableError = computed(() =>
  listStatus.value === 'error' && !Object.keys(error.value?.fields ?? {}).length ? error.value?.message : undefined,
);

const STATUS_LABELS: Record<ProductStatus, string> = { active: 'inventory.common.yes', inactive: 'inventory.common.no', needs_tax_setup: 'inventory.products.filters.unconfigured' };

const columns = computed<DataTableColumn<Product>[]>(() => [
  { key: 'name', label: t('inventory.common.name'), sortable: true, priority: 'high', filter: { type: 'text', maxlength: 200 } },
  { key: 'sku', label: t('inventory.common.sku'), sortable: true, filter: { type: 'text', maxlength: 64 } },
  {
    key: 'price',
    label: t('inventory.common.price'),
    sortable: true,
    align: 'right',
    format: (value) => formatMoney(Number(value), locale.value),
    filter: { type: 'range', amount: true, keys: ['price_min', 'price_max'] },
  },
  { key: 'stock', label: t('inventory.common.stock'), sortable: true, align: 'right', cell: 'stock', filter: { type: 'range', amount: true, keys: ['stock_min', 'stock_max'] } },
  {
    key: 'status',
    label: t('inventory.common.status'),
    align: 'center',
    cell: 'status',
    filter: { type: 'select', options: PRODUCT_STATUSES.map((value) => ({ value, label: t(STATUS_LABELS[value]) })) },
  },
]);

const isService = (row: Product): boolean => row.product_type === 'service';
const actions = computed<DataTableAction<Product>[]>(() => [
  { id: 'detail', label: t('inventory.products.actions.detail'), icon: 'ion:information-circle-outline' },
  ...(canMove.value
    ? [
        { id: 'receive', label: t('inventory.products.actions.receive'), icon: 'ion:download-outline', hidden: isService },
        { id: 'count', label: t('inventory.products.actions.count'), icon: 'ion:keypad-outline', hidden: isService },
        // Nothing to write off from an article that does not track its stock (WORKBOOK INVENTORY-F15).
        { id: 'write_off', label: t('inventory.products.actions.writeOff'), icon: 'ion:warning-outline', hidden: (row: Product) => isService(row) || !row.tracks_stock, menuOnly: true },
      ]
    : []),
  ...(canChange.value ? [{ id: 'edit', label: t('inventory.products.actions.edit'), icon: 'ion:create-outline' }] : []),
  ...(canDelete.value
    ? [{ id: 'delete', label: t('inventory.products.actions.delete'), icon: 'ion:trash-outline', color: 'danger', menuOnly: true }]
    : []),
]);

// ── Dialogs ───────────────────────────────────────────────────────────────────────────────────────
const pageError = ref('');
const formOpen = ref(false);
const editing = ref<Product | null>(null);
const detailOpen = ref(false);
const stockOpen = ref(false);
const stockKind = ref<StockAction>('receive');
/** The product a dialog is about, by id: the live row once it changes (a sale, a count elsewhere). */
const focusedId = ref<string | null>(null);
const focusedSnapshot = ref<Product | null>(null);
const focused = computed(() => rows.value.find((row) => row.id === focusedId.value) ?? focusedSnapshot.value);

function focus(row: Product): void {
  focusedId.value = row.id;
  focusedSnapshot.value = row;
}

function openForm(row: Product | null): void {
  editing.value = row;
  formOpen.value = true;
}

function openDetail(row: Product): void {
  focus(row);
  detailOpen.value = true;
}

function openStock(kind: StockAction, row: Product | null = focused.value): void {
  if (!row) return;
  focus(row);
  detailOpen.value = false;
  stockKind.value = kind;
  stockOpen.value = true;
}

const update = useCommand('inventory.product.update');
const remove = useCommand('inventory.product.delete');

/** Bumped per product when the server refuses its switch: a fresh switch shows the saved state again. */
const switchRevision = ref<Record<string, number>>({});

async function setActive(row: Product, active: boolean): Promise<void> {
  pageError.value = '';
  try {
    await update.run({ id: row.id, is_active: active });
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : t('inventory.products.updateError');
    // The switch flipped under the finger; the product did not change: put it back where it was.
    switchRevision.value = { ...switchRevision.value, [row.id]: (switchRevision.value[row.id] ?? 0) + 1 };
  }
}

async function askDelete(row: Product): Promise<void> {
  const yes = await confirm({
    title: t('inventory.products.delete.title'),
    message: t('inventory.products.delete.message', { name: row.name, sku: row.sku }),
    confirmLabel: t('inventory.products.delete.confirm'),
    tone: 'danger',
  });
  if (!yes) return;
  pageError.value = '';
  try {
    await remove.run({ id: row.id });
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : t('inventory.products.deleteError');
  }
}

function onAction(event: DataTableActionEvent<Product>): void {
  const { actionId, row } = event;
  if (actionId === 'detail') openDetail(row);
  else if (actionId === 'receive' || actionId === 'count' || actionId === 'write_off') openStock(actionId, row);
  else if (actionId === 'edit') openForm(row);
  else if (actionId === 'delete') void askDelete(row);
}

/** The business's «Track stock», what a new item follows (best effort: only managers read settings). */
const hubTracksStock = ref(true);
onMounted(() => {
  if (!session.can('inventory.manage_settings')) return;
  client.api.call('inventory.config.get', {}).then(
    (config) => (hubTracksStock.value = config.track_stock),
    () => undefined, // the server decides anyway; the checkbox then shows the factory value
  );
});

// ── Import and export (INVENTORY-F09, F11) ───────────────────────────────────────────────────────
const importer = useProductImport();
const reportOpen = ref(false);
watch(importer.phase, (phase) => {
  if (phase === 'done') reportOpen.value = true;
});
watch(importer.error, (message) => {
  if (message) pageError.value = message;
});
const previewOpen = computed({ get: () => importer.phase.value === 'preview', set: (open) => !open && importer.cancel() });
const taxOpen = computed({ get: () => importer.phase.value === 'tax', set: (open) => !open && importer.cancel() });

async function importFile(text: string): Promise<void> {
  pageError.value = '';
  await importer.start(text);
}

const exporting = ref(false);
async function exportFile(): Promise<void> {
  pageError.value = '';
  exporting.value = true;
  try {
    const file = await client.api.call('inventory.product.export', { ...listFilters(), ...table.params.value });
    saveTextFile(file.filename, file.content, file.content_type);
  } catch (failure) {
    pageError.value = failure instanceof Error ? failure.message : t('inventory.products.exportError');
  } finally {
    exporting.value = false;
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
      v-if="listStatus === 'reconnecting'"
      tone="warning"
      data-testid="inventory-products-reconnecting"
    >
      {{ $t('inventory.live.reconnecting') }}
    </InlineFeedback>
    <InlineFeedback
      v-if="pageError"
      tone="danger"
      data-testid="inventory-products-page-error"
    >
      {{ pageError }}
    </InlineFeedback>
    <InlineFeedback
      v-if="importer.progress.value"
      tone="info"
      data-testid="inventory-products-import-progress"
    >
      {{ $t('inventory.import.progress', importer.progress.value) }}
      <ion-progress-bar :value="importer.progress.value.total ? importer.progress.value.done / importer.progress.value.total : 0" />
      <template #actions>
        <ion-button
          size="small"
          fill="clear"
          data-testid="inventory-products-import-stop"
          @click="importer.stop()"
        >
          {{ $t('inventory.import.stop') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <InlineFeedback
      v-if="inactive"
      tone="warning"
      data-testid="inventory-products-inactive"
      :heading="$t('inventory.live.appInactive')"
    >
      {{ error?.message }}
    </InlineFeedback>
    <DataTable
      v-else
      v-model:search="table.search.value"
      v-model:filters="filters"
      testid="inventory-products"
      fill
      server-side
      searchable
      filterable
      :filter-errors="filterErrors"
      row-clickable
      :rows="rows"
      :total="result?.total ?? 0"
      :page="table.page.value"
      :page-size="table.pageSize.value"
      :sort="table.sortKey.value"
      :sort-dir="table.sortDir.value"
      :views="['table', 'cards']"
      :card-title="(row: Product) => row.name"
      :columns="columns"
      :actions="actions"
      :addable="canAdd"
      :loading="listStatus === 'loading'"
      :error="tableError"
      :search-placeholder="$t('inventory.products.search')"
      :labels="{ add: $t('inventory.products.new'), loadError: $t('inventory.products.loadError'), retry: $t('inventory.live.retry') }"
      @page-change="table.goToPage"
      @load-more="table.loadMore"
      @page-size-change="table.setPageSize"
      @sort-change="table.setSort"
      @row-click="openDetail"
      @action="onAction"
      @add="openForm(null)"
      @retry="refresh()"
    >
      <template #toolbar>
        <CsvButtons
          testid="inventory-products"
          :importable="canImport"
          :exportable="canExport"
          :busy="exporting || importer.phase.value === 'running'"
          @import="importFile"
          @export="exportFile"
          @read-error="pageError = $t('inventory.import.readError')"
        />
      </template>
      <template #stock="{ row }">
        <span data-testid="inventory-product-stock">{{ row.tracks_stock ? formatQuantity(row.stock, locale) : '—' }}</span>
      </template>
      <template #status="{ row }">
        <ion-chip
          v-if="row.needs_tax_setup"
          color="warning"
          class="inventory-products__unconfigured"
          :disabled="!canChange"
          :title="$t('inventory.tax.unconfiguredReason')"
          :data-testid="`inventory-products-unconfigured-${row.id}`"
          @click.stop="canChange && openForm(row)"
        >
          <HubIcon name="ion:alert-circle-outline" />
          <ion-label><span>{{ `${$t('inventory.tax.unconfigured')} · ${$t('inventory.tax.unconfiguredReason')}` }}</span></ion-label>
        </ion-chip>
        <ion-toggle
          v-else-if="canChange"
          :key="`${row.id}-${switchRevision[row.id] ?? 0}`"
          color="success"
          :aria-label="$t('inventory.products.active')"
          :model-value="row.is_active"
          :data-testid="`inventory-products-active-${row.id}`"
          @click.stop
          @update:model-value="setActive(row, !!$event)"
        />
        <span
          v-else
          :data-testid="`inventory-products-active-text-${row.id}`"
        >{{ row.is_active ? $t('inventory.common.yes') : $t('inventory.common.no') }}</span>
      </template>
      <template #empty>
        <EmptyState
          data-testid="inventory-products-empty"
          icon="cube-outline"
          :heading="table.filtered.value ? $t('inventory.products.noResults') : $t('inventory.products.empty')"
          :message="!table.filtered.value && canAdd ? $t('inventory.products.emptyMessage') : undefined"
        />
      </template>
    </DataTable>

    <ProductFormModal
      v-if="canAdd || canChange"
      v-model:open="formOpen"
      :product="editing"
      :units="units"
      :hub-tracks-stock="hubTracksStock"
    />
    <ProductDetailModal
      v-model:open="detailOpen"
      :product="focused"
      @stock="openStock"
    />
    <StockModal
      v-if="canMove"
      v-model:open="stockOpen"
      :kind="stockKind"
      :product="focused"
      :units="units"
    />
    <ImportPreviewModal
      v-model:open="previewOpen"
      :table="importer.table.value"
      :mapping="importer.mapping.value"
      :required-mapped="importer.requiredMapped.value"
      :rehearsal="importer.rehearsal.value"
      :pending="importer.busy.value"
      @set-mapping="importer.setMapping"
      @confirm="importer.confirm()"
      @cancel="importer.cancel()"
    />
    <ImportTaxModal
      v-model:open="taxOpen"
      :unresolved="importer.unresolved.value"
      :pending="importer.busy.value"
      @set-choice="importer.setChoice"
      @confirm="importer.confirmTax()"
      @cancel="importer.cancel()"
    />
    <ImportReportModal
      v-model:open="reportOpen"
      :report="importer.report.value"
    />
  </AppPage>
</template>

<style scoped>
.inventory-products__unconfigured {
  margin: 0;
  cursor: pointer;
}
</style>
