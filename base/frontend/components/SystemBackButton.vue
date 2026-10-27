<script setup lang="ts">
// The installed app's Back button (BASE-F05, gh:hub#1906): taken beside the pane (`chrome.background`) while a person
// is signed in, and let go when they sign out. A press closes what is open on top, else goes up: a detail view's own
// Back, Home from the root of an app (the way the menu's «Home» goes), out of the app from Home (`lib/system-back.ts`).
// Only inside the installed app; in a browser nothing is registered. It paints nothing.
import { useShellConfig } from '@erplora/ui/shell';
import { useIonRouter } from '@ionic/vue';
import { onBeforeUnmount, onMounted } from 'vue';
import { useRouter } from 'vue-router';

import { installSystemBackButton } from '../lib/system-back';

const router = useRouter();
const ionRouter = useIonRouter();
const { homePath } = useShellConfig();

let release: (() => void) | null = null;
let gone = false;

onMounted(async () => {
  const letGo = await installSystemBackButton({
    atHome: () => router.currentRoute.value.path === homePath,
    goHome: () => ionRouter.navigate(homePath, 'root', 'push'),
  });
  // Gone while the app was answering: the button goes back at once.
  if (gone) letGo?.();
  else release = letGo;
});

onBeforeUnmount(() => {
  gone = true;
  release?.();
});
</script>

<template>
  <span
    hidden
    data-testid="system-back"
  />
</template>
