<script setup lang="ts">
// «Import result» (WORKBOOK INVENTORY-F09/F10), the old report modal of the product and category
// imports: «Rows», «Created», «Skipped (already existed)», «Failed», one line per failed row
// («Line N · SKU — reason»), «Copy report» to fix the file and try again, and the notes (an import
// stopped halfway, what Taxes could not save).
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';

import { useT } from '../composables/useT';
import { type ImportReport, reportText } from '../lib/import-report';

const props = defineProps<{ report: ImportReport | null }>();
const open = defineModel<boolean>('open', { default: false });

const { t } = useT();

function copy(): void {
  if (props.report) void navigator.clipboard?.writeText(reportText(props.report, t));
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="$t('inventory.import.reportTitle')"
    testid="inventory-import-report"
  >
    <template v-if="report">
      <InlineFeedback
        v-if="report.cancelled"
        tone="warning"
        data-testid="inventory-import-report-cancelled"
      >
        {{ $t('inventory.import.cancelledNote') }}
      </InlineFeedback>
      <InlineFeedback
        v-for="note in report.notes"
        :key="note"
        tone="warning"
        data-testid="inventory-import-report-note"
      >
        {{ note }}
      </InlineFeedback>
      <ion-list lines="full">
        <ion-item data-testid="inventory-import-report-count-rows">
          <ion-label>{{ $t('inventory.import.rows') }}</ion-label>
          <ion-note slot="end">
            {{ report.total }}
          </ion-note>
        </ion-item>
        <ion-item data-testid="inventory-import-report-count-created">
          <ion-label>{{ $t('inventory.import.created') }}</ion-label>
          <ion-note
            slot="end"
            color="success"
          >
            {{ report.created }}
          </ion-note>
        </ion-item>
        <ion-item data-testid="inventory-import-report-count-skipped">
          <ion-label>{{ $t('inventory.import.skipped') }}</ion-label>
          <ion-note slot="end">
            {{ report.skipped }}
          </ion-note>
        </ion-item>
        <ion-item data-testid="inventory-import-report-count-failed">
          <ion-label>{{ $t('inventory.import.failed') }}</ion-label>
          <ion-note
            slot="end"
            :color="report.failed.length ? 'danger' : 'success'"
          >
            {{ report.failed.length }}
          </ion-note>
        </ion-item>
      </ion-list>
      <ul
        v-if="report.failed.length"
        class="import-report__failed"
      >
        <li
          v-for="row in report.failed"
          :key="`${row.line}-${row.key}`"
          data-testid="inventory-import-report-failed-line"
        >
          {{ $t('inventory.import.failedLine', { line: row.line, key: row.key || '—', reason: row.reason }) }}
        </li>
      </ul>
    </template>
    <template #footer="{ cancel }">
      <ion-button
        v-if="report?.failed.length"
        fill="outline"
        data-testid="inventory-import-report-copy"
        @click="copy"
      >
        {{ $t('inventory.import.copy') }}
      </ion-button>
      <ion-button
        data-testid="inventory-import-report-close-button"
        @click="cancel"
      >
        {{ $t('inventory.common.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.import-report__failed {
  margin: 12px 0 0;
  padding-left: 1.1rem;
  font-size: 0.875rem;
}

.import-report__failed li + li {
  margin-top: 4px;
}
</style>
