<script setup lang="ts">
// The CSV buttons of an inventory list, the old table's «Import CSV» / «Export CSV» (WORKBOOK
// INVENTORY-F09/F10/F11), each only for whoever may use it. Import picks a file and hands the page
// its text, decoded as Excel saves it; export asks the page to export (the server writes the file).
// They go in DataTable's `toolbar` slot until the table has its own (UI-REQUESTS.md).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { useTemplateRef } from 'vue';

import { decodeCsv } from '../lib/csv';

withDefaults(defineProps<{ importable?: boolean; exportable?: boolean; busy?: boolean; testid: string }>(), {
  importable: false,
  exportable: false,
  busy: false,
});

const emit = defineEmits<{ import: [text: string]; export: []; readError: [message: string] }>();

const input = useTemplateRef<HTMLInputElement>('input');

async function picked(): Promise<void> {
  const file = input.value?.files?.[0];
  if (!file) return;
  try {
    emit('import', decodeCsv(await file.arrayBuffer()));
  } catch (error) {
    emit('readError', error instanceof Error ? error.message : String(error));
  } finally {
    if (input.value) input.value.value = '';
  }
}
</script>

<template>
  <span class="csv-buttons">
    <template v-if="importable">
      <ion-button
        fill="clear"
        size="small"
        :data-testid="`${testid}-csv-import-button`"
        :aria-label="$t('inventory.common.importCsv')"
        :title="$t('inventory.common.importCsv')"
        :disabled="busy"
        @click="input?.click()"
      >
        <HubIcon
          slot="icon-only"
          name="ion:cloud-outline"
        />
      </ion-button>
      <input
        ref="input"
        class="csv-buttons__file"
        type="file"
        accept=".csv,text/csv"
        hidden
        :data-testid="`${testid}-csv-import`"
        @change="picked"
      >
    </template>
    <ion-button
      v-if="exportable"
      fill="clear"
      size="small"
      :data-testid="`${testid}-csv-export`"
      :aria-label="$t('inventory.common.exportCsv')"
      :title="$t('inventory.common.exportCsv')"
      :disabled="busy"
      @click="emit('export')"
    >
      <HubIcon
        slot="icon-only"
        name="ion:download-outline"
      />
    </ion-button>
  </span>
</template>

<style scoped>
.csv-buttons {
  display: inline-flex;
  align-items: center;
}
</style>
