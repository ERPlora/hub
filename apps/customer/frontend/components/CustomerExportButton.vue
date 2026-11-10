<script setup lang="ts">
// «Export CSV» of the customer list's toolbar (CUSTOMER-F09): the server builds `customers.csv` with
// EVERY card matching the search and filters (not just the page shown) and checks the permission;
// the Hub's `saveFile` hands it over (the browser's downloads, or the installed app's, which says where; hub#1041).
// A byte-order mark goes first so a spreadsheet reads the accents.
import { useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { ref } from 'vue';

import { saveFile } from '../../../../base/frontend/lib/download';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomerFilters } from '../operations';

const props = defineProps<{ filters: CustomerFilters }>();

const client = useLiveClient();
const { t } = useCustomerI18n();
const pending = ref(false);

async function exportCsv(): Promise<void> {
  pending.value = true;
  try {
    const file = await client.api.call('customer.customer.export', props.filters);
    await saveFile(file.filename, new Blob([`﻿${file.csv}`], { type: file.content_type }), t);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    void toastError(t('customer.exportCsv.failed', { reason }));
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <ion-button
    class="customer-csv-button"
    size="small"
    fill="outline"
    data-testid="customer-export"
    :disabled="pending"
    @click="exportCsv"
  >
    <HubIcon
      slot="start"
      name="ion:download-outline"
    />
    {{ $t('customer.exportCsv.button') }}
  </ion-button>
</template>

<style scoped>
.customer-csv-button {
  margin: 0;
}
</style>
