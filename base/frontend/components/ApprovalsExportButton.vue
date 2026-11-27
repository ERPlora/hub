<script setup lang="ts">
// «Export CSV» in the bar of Employees › Approvals (BASE-F85; the old hub exported its record): the server writes
// `approvals.csv` with every approval the list's search and filters keep, not only the newest it shows, in the
// person's language, and checks the permission; the shared ExportButton hands it over (the browser's downloads, or the
// installed app's, which says where; hub#1041), with a byte-order mark first so a spreadsheet reads the accents. While
// it works it says so and takes no second click; a refusal is told with its reason.
import { useLiveClient } from '@erplora/ui/sdk';

import { useBaseI18n } from '../lib/i18n';
import type { ApprovalExportQuery } from '../operations/approvals';
import ExportButton from './ExportButton.vue';

const props = defineProps<{ query: ApprovalExportQuery }>();

const client = useLiveClient();
const { t } = useBaseI18n();

async function load(): Promise<{ filename: string; blob: Blob }> {
  const file = await client.api.call('base.approval.export', props.query);
  return { filename: file.filename, blob: new Blob([`\uFEFF${file.csv}`], { type: file.content_type }) };
}
</script>

<template>
  <ExportButton
    testid="approvals-export"
    :label="t('base.approvals.export.button')"
    :pending-label="t('base.approvals.export.pending')"
    :failed="(reason: string) => t('base.approvals.export.failed', { reason })"
    :load="load"
  />
</template>
