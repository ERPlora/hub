<script setup lang="ts">
// base's pieces beside the pane (`createShell({ chrome: { background } })`, mounted once per signed-in person): the
// device's notices (APPOINTMENT-F28) and the assistant's panel (APP-BASE-9).
import AssistantPanel from './assistant/AssistantPanel.vue';
import DeviceNotices from './DeviceNotices.vue';
</script>

<template>
  <DeviceNotices />
  <AssistantPanel />
</template>
