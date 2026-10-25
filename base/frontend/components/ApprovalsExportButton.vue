<script setup lang="ts">
// «Export CSV» in the bar of Employees › Approvals (BASE-F85; the old hub exported its record): the server writes
// `approvals.csv` with every approval the list's search and filters keep, not only the newest it shows, in the
// person's language, and checks the permission; this hands the file to the browser, with a byte-order mark first so a
// spreadsheet reads the accents. While it works it says so and takes no second click; a refusal is told with its reason.
import { useLiveClient } from '@erplora/ui/sdk';
import { HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { ref } from 'vue';

import { saveFile } from '../lib/data';
import { useBaseI18n } from '../lib/i18n';
import type { ApprovalExportQuery } from '../operations';

const props = defineProps<{ query: ApprovalExportQuery }>();

const client = useLiveClient();
const { t } = useBaseI18n();
const pending = ref(false);

async function exportCsv(): Promise<void> {
  pending.value = true;
  try {
    const file = await client.api.call('base.approval.export', props.query);
    saveFile(file.filename, new Blob([`﻿${file.csv}`], { type: file.content_type }));
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    void toastError(t('base.approvals.export.failed', { reason }));
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <ion-button
    class="approvals-export"
    size="small"
    fill="outline"
    data-testid="approvals-export"
    :disabled="pending"
    @click="exportCsv"
  >
    <HubIcon
      slot="start"
      name="ion:download-outline"
    />
    {{ pending ? t('base.approvals.export.pending') : t('base.approvals.export.button') }}
  </ion-button>
</template>

<style scoped>
.approvals-export {
  margin: 0;
}
</style>
