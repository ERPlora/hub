<script setup lang="ts">
// Files › the preview of a table (hub#578, BASE-F74): a CSV, a TSV or each sheet of a spreadsheet as a table whose
// first row is the header, its cells always as text. A spreadsheet with several sheets shows one tab per sheet, as
// Excel and Google Sheets do; each one its first rows (`TABLE_PREVIEW_ROWS`), saying when it has more; an empty one
// says so.
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { type PreviewSheet, TABLE_PREVIEW_ROWS } from '../lib/files';
import { useBaseI18n } from '../lib/i18n';
import '../file-viewers.css';

const props = defineProps<{ sheets: readonly PreviewSheet[] }>();

const { t } = useBaseI18n();

const picked = ref(0);
watch(
  () => props.sheets,
  () => {
    picked.value = 0;
  },
);
const sheet = computed<PreviewSheet | undefined>(() => props.sheets[picked.value] ?? props.sheets[0]);
const header = computed(() => sheet.value?.rows[0] ?? []);
const body = computed(() => sheet.value?.rows.slice(1) ?? []);

function pick(event: CustomEvent<{ value?: string | number }>): void {
  picked.value = Number(event.detail.value ?? 0);
}
</script>

<template>
  <div class="file-sheets">
    <ion-segment
      v-if="sheets.length > 1"
      class="file-sheets-tabs"
      data-testid="file-preview-sheet-tabs"
      scrollable
      :value="String(picked)"
      :aria-label="t('base.files.preview.sheets')"
      @ion-change="pick"
    >
      <ion-segment-button
        v-for="(each, index) in sheets"
        :key="index"
        :value="String(index)"
        data-testid="file-preview-sheet-tab"
      >
        <ion-label>{{ each.name }}</ion-label>
      </ion-segment-button>
    </ion-segment>
    <p
      v-if="sheet?.cut"
      class="file-sheets-muted"
      data-testid="file-preview-cut"
    >
      {{ t('base.files.preview.tableCut', { shown: TABLE_PREVIEW_ROWS }) }}
    </p>
    <p
      v-if="!header.length"
      class="file-sheets-muted"
      data-testid="file-preview-sheet-empty"
    >
      {{ t('base.files.preview.sheetEmpty') }}
    </p>
    <div
      v-else
      class="file-sheets-wrap"
    >
      <table
        class="file-sheets-table"
        data-testid="file-preview-table"
      >
        <thead>
          <tr>
            <th
              v-for="(cell, index) in header"
              :key="index"
            >
              {{ cell }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, index) in body"
            :key="index"
          >
            <td
              v-for="(cell, column) in row"
              :key="column"
            >
              {{ cell }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

