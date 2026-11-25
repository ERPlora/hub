<script setup lang="ts">
// What the signed-in person may do, followed on every screen beside the pane (BackgroundChrome): the live
// `base.session.access` answers a key of their permissions and re-runs when erplora.com's photo changes their role.
// When the key changes, base reads the session again (`sessionChanged`, frontend/main.ts), so the menu, «My apps» and
// the tabs follow the new role without signing in again; a screen in front that the session read again closes or opens
// goes through the app gate again (`lib/app-gate.ts`): «No access» in the same address, or the screen. It paints
// nothing.
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { watch } from 'vue';
import { useRouter } from 'vue-router';

import { gateAgain, gateVerdict } from '../lib/app-gate';
import { readSessionAgainOnChange } from '../lib/session-follow';

const router = useRouter();
const session = useSession();
const { data } = useLive('base.session.access', {});

readSessionAgainOnChange(() => data.value?.key);

/** Whether `me` closes the screen in front to this person, judged on the app's own route as the gate judges it. */
function closedBy(me: typeof session.me.value): boolean {
  return gateVerdict(me, router.resolve(router.currentRoute.value.fullPath)) === 'no-access';
}

watch(
  () => session.me.value,
  (me, before) => {
    if (closedBy(me) !== closedBy(before)) gateAgain(router);
  },
);
</script>

<template>
  <span
    hidden
    data-testid="access-follower"
  />
</template>
