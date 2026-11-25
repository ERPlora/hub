<script setup lang="ts">
// The person's own language followed on every screen beside the pane (BackgroundChrome): the live `base.profile.get`
// re-runs when their profile changes, also when the assistant's card changed it. The language the app speaks is the
// session's, which is no live query: when the language kept in «My profile» changes, base reads the session again
// (`sessionChanged`, frontend/main.ts) and the shell follows its language, as «My profile»'s own selector does. It
// paints nothing.
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { watch } from 'vue';

import { sessionChanged } from '../lib/access';
import { readSessionAgainOnChange } from '../lib/session-follow';

const session = useSession();
const { data } = useLive('base.profile.get', {});
const chosen = () => data.value?.language;

readSessionAgainOnChange(chosen);

// A language chosen while this page was still loading its live answers comes as the first answer: the session is read
// again if it does not speak it yet. The business's ('') names no language this page knows.
watch(
  chosen,
  (language) => {
    if (language && language !== session.me.value?.language) sessionChanged();
  },
  { once: true },
);
</script>

<template>
  <span
    hidden
    data-testid="language-follower"
  />
</template>
