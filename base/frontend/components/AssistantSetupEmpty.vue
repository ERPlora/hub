<script setup lang="ts">
// The Hub's empty conversation of the assistant (BASE-G111, G121; the old hub's empty drawer), in the shared panel's
// `empty` slot (BackgroundChrome): the sentence — the setup's when the panel was opened from «Finish setting up your
// business» — and the shortcuts: «What is left to set up?» and, for up to four pending steps this person can do,
// «How do I set up “…”?», each asked at once with the setup. The checklist is read live while this shows; if it
// cannot be read, only the first shortcut stays.
import { AssistantEmpty } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { computed } from 'vue';

import { setupShortcuts } from '../lib/assistant-hub';
import { useBaseI18n } from '../lib/i18n';

const props = defineProps<{
  /** The panel was opened for the setup. */
  setup: boolean;
  /** The panel's `ask` (its slot's). */
  ask: (text: string, options?: { setup?: boolean }) => void;
}>();

const { t } = useBaseI18n();
const { data } = useLive('base.setup.status', {});

const shortcuts = computed(() =>
  setupShortcuts(data.value).map((shortcut) => (shortcut.title ? t(shortcut.key, { title: shortcut.title }) : t(shortcut.key))),
);
</script>

<template>
  <AssistantEmpty
    :text="setup ? t('base.assistant.setupIntro') : t('base.assistant.empty')"
    :shortcuts="shortcuts"
    @ask="(text: string) => props.ask(text, { setup: true })"
  />
</template>
