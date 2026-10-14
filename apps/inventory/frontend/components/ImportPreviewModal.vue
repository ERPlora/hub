<script setup lang="ts">
// «Check the import» (WORKBOOK INVENTORY-F09, step 1), the old preview, nothing created yet: one
// select per column of the file («Do not import» or the field; Name and SKU carry an asterisk), the
// first rows under the field each column goes to (the table scrolls sideways on its own), and the
// server's rehearsal of the whole file with up to ten reasons. The importer (useProductImport) owns
// the state: this dialog shows it and says what the person picked.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { IonSelect, IonSelectOption, IonSpinner } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import type { Rehearsal } from '../composables/useProductImport';
import type { CsvTable } from '../lib/csv';
import { PRODUCT_IMPORT_FIELDS, PRODUCT_IMPORT_REQUIRED, type ProductImportField } from '../lib/import-mapping';

/** Rows shown: enough to see the mapping is right, few enough to fit. */
const PREVIEW_ROWS = 5;
/** Reasons listed under the summary. */
const REASONS = 10;

const props = withDefaults(
  defineProps<{
    table: CsvTable | null;
    mapping: readonly (ProductImportField | '')[];
    requiredMapped: boolean;
    rehearsal: Rehearsal;
    /** The import is under way: it cannot be launched twice. */
    pending?: boolean;
  }>(),
  { pending: false },
);
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ setMapping: [index: number, field: ProductImportField | '']; confirm: []; cancel: [] }>();

const { t } = useT();

const FIELD_KEYS: Record<ProductImportField, string> = {
  name: 'inventory.form.name',
  sku: 'inventory.form.sku',
  price: 'inventory.form.price',
  cost: 'inventory.form.cost',
  stock: 'inventory.common.stock',
  low_stock_threshold: 'inventory.form.threshold',
  ean13: 'inventory.form.ean13',
  description: 'inventory.form.description',
  unit: 'inventory.form.unit',
  tax_category_key: 'inventory.tax.label',
};
const fieldLabel = (field: ProductImportField): string => t(FIELD_KEYS[field]);
const optionLabel = (field: ProductImportField): string =>
  PRODUCT_IMPORT_REQUIRED.includes(field) ? t('inventory.import.required', { field: fieldLabel(field) }) : fieldLabel(field);

const shown = computed(() => props.table?.rows.slice(0, PREVIEW_ROWS) ?? []);
const report = computed(() => props.rehearsal.report);
const ready = computed(() => (props.rehearsal.status === 'ready' ? (report.value?.ready ?? 0) : 0));
const canImport = computed(() => props.requiredMapped && props.rehearsal.status === 'ready' && ready.value > 0);

function pick(index: number, value: unknown): void {
  const field = (PRODUCT_IMPORT_FIELDS as readonly string[]).includes(String(value)) ? (value as ProductImportField) : '';
  if (field !== props.mapping[index]) emit('setMapping', index, field);
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="$t('inventory.import.previewTitle')"
    testid="inventory-import-preview"
    :submit-label="$t('inventory.import.confirm', { n: ready })"
    :submit-disabled="!canImport"
    :pending="pending"
    @submit="emit('confirm')"
    @cancel="emit('cancel')"
  >
    <p class="import-preview__hint">
      {{ $t('inventory.import.previewHint') }}
    </p>
    <div class="import-preview__columns">
      <ion-select
        v-for="(header, index) in table?.headers ?? []"
        :key="`${index}-${header}`"
        data-testid="inventory-import-column"
        :model-value="mapping[index] ?? ''"
        :label="header"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        @update:model-value="pick(index, $event)"
      >
        <ion-select-option value="">
          {{ $t('inventory.import.ignore') }}
        </ion-select-option>
        <ion-select-option
          v-for="field in PRODUCT_IMPORT_FIELDS"
          :key="field"
          :value="field"
        >
          {{ optionLabel(field) }}
        </ion-select-option>
      </ion-select>
    </div>

    <h3
      class="import-preview__title"
      data-testid="inventory-import-rows-title"
    >
      {{ $t('inventory.import.rowsTitle', { n: shown.length, total: table?.rows.length ?? 0 }) }}
    </h3>
    <div class="import-preview__scroll">
      <table data-testid="inventory-import-preview-table">
        <thead>
          <tr>
            <th
              v-for="(header, index) in table?.headers ?? []"
              :key="`${index}-${header}`"
            >
              <template v-if="mapping[index]">
                {{ fieldLabel(mapping[index] as ProductImportField) }}
              </template>
              <s v-else>{{ header }}</s>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in shown"
            :key="row.line"
          >
            <td
              v-for="(value, index) in row.values"
              :key="index"
            >
              {{ value }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <InlineFeedback
      v-if="!requiredMapped"
      tone="danger"
      data-testid="inventory-import-missing"
    >
      {{ $t('inventory.import.missingRequired') }}
    </InlineFeedback>
    <p
      v-else-if="rehearsal.status === 'checking'"
      class="import-preview__checking"
      data-testid="inventory-import-checking"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      {{ $t('inventory.import.checking') }}
    </p>
    <InlineFeedback
      v-else-if="rehearsal.status === 'error'"
      tone="danger"
      :heading="$t('inventory.import.checkError')"
    >
      {{ rehearsal.error }}
    </InlineFeedback>
    <InlineFeedback
      v-else-if="report"
      :tone="report.failed.length ? 'warning' : 'success'"
      data-testid="inventory-import-summary"
    >
      {{ $t('inventory.import.summary', { ready: report.ready, failed: report.failed.length }) }}
      <ul
        v-if="report.failed.length"
        class="import-preview__reasons"
      >
        <li
          v-for="row in report.failed.slice(0, REASONS)"
          :key="`${row.line}-${row.key}`"
          data-testid="inventory-import-reason"
        >
          {{ $t('inventory.import.lineReason', { line: row.line, reason: row.reason }) }}
        </li>
      </ul>
      <p
        v-if="report.skipped"
        class="import-preview__skipped"
        data-testid="inventory-import-skipped"
      >
        {{ $t('inventory.import.skippedNote', { n: report.skipped }) }}
      </p>
    </InlineFeedback>
  </FormModal>
</template>

<style scoped>
.import-preview__hint {
  margin: 0 0 12px;
}

.import-preview__columns {
  display: grid;
  gap: 8px;
}

.import-preview__title {
  margin: 16px 0 6px;
  font-size: 0.95rem;
}

.import-preview__scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  margin-bottom: 12px;
}

.import-preview__scroll table {
  min-width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}

.import-preview__scroll th,
.import-preview__scroll td {
  padding: 0.3rem 0.5rem;
  text-align: left;
  white-space: nowrap;
  border-bottom: 1px solid var(--ion-color-step-150, #e3e3e3);
}

.import-preview__checking {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.import-preview__reasons {
  margin: 0.3rem 0 0;
  padding-left: 1.1rem;
}

.import-preview__skipped {
  margin: 0.3rem 0 0;
}
</style>
