<script setup lang="ts">
// «Import CSV» of the customer list's toolbar (CUSTOMER-F08): opens the file picker for a CSV and
// hands the file up; the page imports it (`useCustomerImport`). Off while an import runs.
import { HubIcon } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { useTemplateRef } from 'vue';

defineProps<{ busy: boolean }>();
const emit = defineEmits<{ pick: [file: File] }>();

const input = useTemplateRef<HTMLInputElement>('input');

function onChange(): void {
  const file = input.value?.files?.[0];
  if (file) emit('pick', file);
  // The same file can be picked again (after fixing it).
  if (input.value) input.value.value = '';
}
</script>

<template>
  <ion-button
    class="customer-csv-button"
    size="small"
    fill="outline"
    data-testid="customer-import"
    :disabled="busy"
    @click="input?.click()"
  >
    <HubIcon
      slot="start"
      name="ion:cloud-upload-outline"
    />
    {{ $t('customer.importCsv.button') }}
  </ion-button>
  <input
    ref="input"
    type="file"
    accept=".csv,text/csv"
    hidden
    @change="onChange"
  >
</template>

<style scoped>
.customer-csv-button {
  margin: 0;
}
</style>
