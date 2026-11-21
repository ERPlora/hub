<script setup lang="ts">
// base's piece at the end of the topbar (`createShell({ chrome: { topbar } })`), before the shell's bell: the
// assistant's sparkles and, inside the installed app, «Change business». On a phone the shell lists them in its «⋮»
// beside «My apps».
import { AssistantButton } from '@erplora/ui/components';

import ChangeBusinessButton from './ChangeBusinessButton.vue';
</script>

<template>
  <AssistantButton />
  <ChangeBusinessButton />
</template>
