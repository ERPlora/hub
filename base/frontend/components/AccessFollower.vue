<script setup lang="ts">
// What the signed-in person may do, followed on every screen beside the pane (BackgroundChrome): the live
// `base.session.access` answers a key of their permissions and re-runs when erplora.com's photo changes their role.
// When the key changes, base reads the session again (`sessionChanged`, frontend/main.ts), so the menu, «My apps» and
// the tabs follow the new role without signing in again. It paints nothing.
import { useLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

import { sessionChanged } from '../lib/access';

const { data } = useLive('base.session.access', {});

watch(
  () => data.value?.key,
  (next, previous) => {
    if (next !== undefined && previous !== undefined && next !== previous) sessionChanged();
  },
);
</script>

<template>
  <span
    hidden
    data-testid="access-follower"
  />
</template>
