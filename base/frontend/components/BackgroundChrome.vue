<script setup lang="ts">
// base's pieces beside the pane (`createShell({ chrome: { background } })`, mounted once per signed-in person): the
// device's notices (APPOINTMENT-F28), the assistant's panel (APP-BASE-9), the business's apps followed live, so the
// menu follows an app turned on or off on any device (PLAN-HUB §9), and the user menu's «Report a problem» (BASE-F108).
import AppsFollower from './AppsFollower.vue';
import AssistantPanel from './assistant/AssistantPanel.vue';
import DeviceNotices from './DeviceNotices.vue';
import ReportProblemDialog from './ReportProblemDialog.vue';
</script>

<template>
  <DeviceNotices />
  <AssistantPanel />
  <AppsFollower />
  <ReportProblemDialog />
</template>
