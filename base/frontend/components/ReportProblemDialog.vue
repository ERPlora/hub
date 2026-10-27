<script setup lang="ts">
// BASE-F108 · «Report a problem» without leaving the hub (beside the pane, BackgroundChrome): `@erplora/ui`'s dialog,
// opened by the user menu (`lib/report-problem`), sends `base.support.report` with the screen the person is on;
// erplora.com mails its support mailbox and answers the address support writes back to (ACCOUNTS-F38).
import { ReportProblemModal, type ReportProblemReport, type ReportProblemSent } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { useRoute } from 'vue-router';

import { reportProblemOpen } from '../lib/report-problem';

const route = useRoute();
const report = useCommand('base.support.report');

async function send(written: ReportProblemReport): Promise<ReportProblemSent> {
  const sent = await report.run({ ...written, page: route.fullPath });
  return { replyTo: sent.reply_to };
}
</script>

<template>
  <ReportProblemModal
    v-model:open="reportProblemOpen"
    :send="send"
  />
</template>
