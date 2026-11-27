<script setup lang="ts">
// «Export CSV» of the customer list's toolbar (CUSTOMER-F09): the server builds `customers.csv` with
// EVERY card matching the search and filters (not just the page shown) and checks the permission;
// the shared ExportButton hands it over (the browser's downloads, or the installed app's, which says where; hub#1041).
// A byte-order mark goes first so a spreadsheet reads the accents.
import { useLiveClient } from '@erplora/ui/sdk';

import ExportButton from '../../../../base/frontend/components/ExportButton.vue';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { CustomerFilters } from '../operations';

const props = defineProps<{ filters: CustomerFilters }>();

const client = useLiveClient();
const { t } = useCustomerI18n();

async function load(): Promise<{ filename: string; blob: Blob }> {
  const file = await client.api.call('customer.customer.export', props.filters);
  return { filename: file.filename, blob: new Blob([`\uFEFF${file.csv}`], { type: file.content_type }) };
}
</script>

<template>
  <ExportButton
    testid="customer-export"
    :label="t('customer.exportCsv.button')"
    :pending-label="t('customer.exportCsv.button')"
    :failed="(reason: string) => t('customer.exportCsv.failed', { reason })"
    :load="load"
  />
</template>
