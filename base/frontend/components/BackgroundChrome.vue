<script setup lang="ts">
// base's pieces beside the pane (`createShell({ chrome: { background } })`, mounted once per signed-in person): the
// device's notices, the assistant's panel (the shared one of @erplora/ui, configured as
// the Hub's in main.ts, with base's empty conversation and its setup shortcuts), the business's apps followed live, so the
// menu follows an app turned on or off on any device, the user menu's «Report a problem» and
// the installed app's Back button.
import { AssistantPanel } from '@erplora/ui/components';

import AppsFollower from './AppsFollower.vue';
import AssistantSetupEmpty from './AssistantSetupEmpty.vue';
import DeviceNotices from './DeviceNotices.vue';
import ReportProblemDialog from './ReportProblemDialog.vue';
import SystemBackButton from './SystemBackButton.vue';
</script>

<template>
  <DeviceNotices />
  <AssistantPanel>
    <template #empty="{ setup, ask }">
      <AssistantSetupEmpty
        :setup="setup"
        :ask="ask"
      />
    </template>
  </AssistantPanel>
  <AppsFollower />
  <ReportProblemDialog />
  <SystemBackButton />
</template>
