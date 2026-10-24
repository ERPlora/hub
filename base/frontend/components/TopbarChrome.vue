<script setup lang="ts">
// base's piece at the end of the topbar (`createShell({ chrome: { topbar } })`): the assistant's sparkles, then the
// bell, as in the old hub (BASE-G110, BASE-G137).
import AssistantButton from './assistant/AssistantButton.vue';
import HubBell from './HubBell.vue';
</script>

<template>
  <AssistantButton />
  <HubBell />
</template>
