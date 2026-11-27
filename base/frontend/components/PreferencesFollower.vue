<script setup lang="ts">
// The person's own preferences followed on every screen beside the pane (BackgroundChrome): the live `base.profile.get`
// re-runs when their profile changes, also when the assistant's card changed it. The language the app speaks is the
// session's, which is no live query: when the language kept in «My profile» changes, base reads the session again
// (`sessionChanged`, frontend/main.ts) and the shell follows its language, as «My profile»'s own selector does. An
// appearance chosen anew is painted at once, as «My profile» paints it. It paints nothing of its own.
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { watch } from 'vue';

import { sessionChanged } from '../lib/access';
import { paintAppearance } from '../lib/appearance';
import { onChangeAfterFirstAnswer, readSessionAgainOnChange } from '../lib/session-follow';

const session = useSession();
const { data } = useLive('base.profile.get', {});
const chosen = () => data.value?.language;
const appearance = () => (data.value ? `${data.value.theme_mode} ${data.value.palette} ${data.value.ui_scale}` : undefined);

readSessionAgainOnChange(chosen);
onChangeAfterFirstAnswer(appearance, () => {
  if (data.value) paintAppearance(data.value);
});

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
    data-testid="preferences-follower"
  />
</template>
