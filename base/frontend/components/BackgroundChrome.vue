<script setup lang="ts">
// base's pieces beside the pane (`createShell({ chrome: { background } })`, mounted once per signed-in person): the
// device's notices, the assistant's panel (the shared one of @erplora/ui, configured as
// the Hub's in main.ts, with base's empty conversation and its setup shortcuts), the business's apps, the person's
// access and their own language followed live, so the menu follows an app turned on or off on any device and a role
// changed on erplora.com, and the app speaks the language the person chose wherever they chose it (the assistant's card),
// the user menu's «Report a problem», the installed app's
// «Change business?» and its Back button, and the help entry that paints into the visible page's topbar.
import { AssistantPanel } from '@erplora/ui/components';

import AccessFollower from './AccessFollower.vue';
import AppsFollower from './AppsFollower.vue';
import AssistantSetupEmpty from './AssistantSetupEmpty.vue';
import ChangeBusinessDialog from './ChangeBusinessDialog.vue';
import DeviceNotices from './DeviceNotices.vue';
import HelpEntry from './HelpEntry.vue';
import PreferencesFollower from './PreferencesFollower.vue';
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
  <AccessFollower />
  <PreferencesFollower />
  <ReportProblemDialog />
  <ChangeBusinessDialog />
  <SystemBackButton />
  <HelpEntry />
</template>
