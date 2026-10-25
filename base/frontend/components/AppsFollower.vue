<script setup lang="ts">
// The apps of the business followed on every screen (PLAN-HUB §9; BASE-F22), mounted once per signed-in person beside
// the pane (BackgroundChrome): the live `base.app.list`, re-run when an app is turned on or off — here or on another
// device — and when erplora.com's photo changes the rights. The menu is the session's, which is no live query: when
// an app's state changes, base reads the session again (`sessionChanged`, frontend/main.ts), and a screen of an app
// that went off goes through the app gate again (`lib/app-gate.ts`), which shows why it does not open. It paints
// nothing.
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { computed, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { sessionChanged } from '../lib/access';

const route = useRoute();
const router = useRouter();
const session = useSession();
const { data } = useLive('base.app.list', {});

/** Each app's state, the only part of the list that changes the menu. */
const states = computed(() => data.value?.apps.map((app) => `${app.id}:${app.state}`).join(','));

watch(states, (next, previous) => {
  if (next !== undefined && previous !== undefined && next !== previous) sessionChanged();
});

/** The app of the screen in front, off in the session just read: the gate runs again in the same address. */
watch(
  () => session.me.value?.apps,
  (apps) => {
    const app = route.meta.app;
    const entry = app ? apps?.find((candidate) => candidate.label === app) : undefined;
    if (!entry || entry.state === 'on') return;
    void router.replace({ path: route.path, query: route.query, hash: route.hash, force: true });
  },
);
</script>

<template>
  <span
    hidden
    data-testid="apps-follower"
  />
</template>
