<script setup lang="ts">
// base's piece at the end of the topbar (`createShell({ chrome: { topbar } })`), before the shell's bell. On a phone
// the shell lists it in its «⋮» beside «My apps», where the sparkles are the row «Assistant».
import { AssistantButton } from '@erplora/ui/components';
</script>

<template>
  <AssistantButton />
</template>
