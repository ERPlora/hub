<script setup lang="ts">
// The person's own language followed on every screen beside the pane (BackgroundChrome): the live `base.profile.get`
// re-runs when their profile changes, also when the assistant's card changed it. The language the app speaks is the
// session's, which is no live query: when the language kept in «My profile» changes, base reads the session again
// (`sessionChanged`, frontend/main.ts) and the shell follows its language, as «My profile»'s own selector does. It
// paints nothing.
import { useLive } from '@erplora/ui/sdk';

import { readSessionAgainOnChange } from '../lib/session-follow';

const { data } = useLive('base.profile.get', {});

readSessionAgainOnChange(() => data.value?.language);
</script>

<template>
  <span
    hidden
    data-testid="language-follower"
  />
</template>
