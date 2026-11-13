<script setup lang="ts">
// The assistant's empty conversation, in the shared panel's `empty` slot: «What is left to set up?» and a shortcut for
// each of up to four pending setup steps this person can do. If the checklist cannot be read, only the first stays.
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
