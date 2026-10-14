<script setup lang="ts">
// The summary of «Import CSV» (CUSTOMER-F08), as the product painted it above the table: the
// counts, each skipped row with the server's reasons (first 20), the rows to review and any block
// the server refused. Success, warning or danger by what happened; «Close» drops it.
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import type { ImportReport } from '../lib/useCustomerImport';

const props = defineProps<{ report: ImportReport }>();
const emit = defineEmits<{ close: [] }>();

const SHOWN = 20;

const tone = computed(() =>
  props.report.failed.length ? 'danger' : props.report.skipped.length || props.report.warnings.length ? 'warning' : 'success',
);
const skipped = computed(() => props.report.skipped.slice(0, SHOWN));
const warnings = computed(() => props.report.warnings.slice(0, SHOWN));
</script>

<template>
  <InlineFeedback
    class="customer-import-report"
    data-testid="customer-import-report"
    :tone="tone"
  >
    <strong data-testid="customer-import-summary">{{
      $t('customer.importCsv.summary', { total: report.total, created: report.created, skipped: report.skipped.length })
    }}</strong>
    <ul
      v-if="report.skipped.length"
      class="customer-import-report__list"
      data-testid="customer-import-skipped"
    >
      <li
        v-for="row in skipped"
        :key="row.line"
      >
        {{ $t('customer.importCsv.row', { line: row.line }) }}: {{ row.reasons.join(' ') }}
      </li>
      <li v-if="report.skipped.length > skipped.length">
        …
      </li>
    </ul>
    <div
      v-if="report.warnings.length"
      data-testid="customer-import-warnings"
    >
      <p class="customer-import-report__heading">
        {{ $t('customer.importCsv.review') }}
      </p>
      <ul class="customer-import-report__list">
        <li
          v-for="row in warnings"
          :key="row.line"
        >
          {{ $t('customer.importCsv.row', { line: row.line }) }}: {{ row.reasons.join(' ') }}
        </li>
        <li v-if="report.warnings.length > warnings.length">
          …
        </li>
      </ul>
    </div>
    <ul
      v-if="report.failed.length"
      class="customer-import-report__list"
    >
      <li
        v-for="block in report.failed"
        :key="block.from"
        data-testid="customer-import-failed"
      >
        {{ $t('customer.importCsv.failedBlock', { from: block.from, to: block.to, reason: block.reason }) }}
      </li>
    </ul>
    <template #actions>
      <ion-button
        size="small"
        fill="clear"
        data-testid="customer-import-close"
        @click="emit('close')"
      >
        {{ $t('customer.importCsv.close') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>

<style scoped>
.customer-import-report {
  margin-block-end: 0.75rem;
}

.customer-import-report__list {
  margin: 0.25rem 0 0;
  padding-left: 1.1rem;
  font-size: 0.85rem;
  max-height: 9rem;
  overflow: auto;
}

.customer-import-report__heading {
  margin: 0.5rem 0 0;
  font-weight: 600;
  font-size: 0.85rem;
}
</style>
