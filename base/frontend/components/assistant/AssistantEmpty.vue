<script setup lang="ts">
// The empty conversation (BASE-G111, G121; the old hub's empty drawer): the sparkles, the sentence — the setup's when
// the panel was opened from «Finish setting up your business» — and the shortcuts: «What is left to set up?» and, for
// up to four pending steps this person can do, «How do I set up “…”?», each asked at once (`ask`). The checklist is
// read live while this shows; if it cannot be read, only the first shortcut stays.
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { setupShortcuts } from '../../lib/assistant-guide';
import { useBaseI18n } from '../../lib/i18n';

defineProps<{ setup: boolean }>();
const emit = defineEmits<{ ask: [text: string] }>();

const { t } = useBaseI18n();
const { data } = useLive('base.setup.status', {});

const shortcuts = computed(() =>
  setupShortcuts(data.value).map((shortcut) => (shortcut.title ? t(shortcut.key, { title: shortcut.title }) : t(shortcut.key))),
);
</script>

<template>
  <div
    class="assistant-empty"
    data-testid="assistant-empty"
  >
    <HubIcon
      class="assistant-empty-icon"
      name="ion:sparkles-outline"
    />
    <p class="assistant-empty-text">
      {{ setup ? t('base.assistant.setupIntro') : t('base.assistant.empty') }}
    </p>
    <div class="assistant-empty-shortcuts">
      <button
        v-for="text in shortcuts"
        :key="text"
        type="button"
        class="assistant-shortcut"
        data-testid="assistant-shortcut"
        @click="emit('ask', text)"
      >
        {{ text }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.assistant-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 4px 16px;
  text-align: center;
}
.assistant-empty-icon {
  font-size: 40px;
  color: var(--ion-color-primary);
}
.assistant-empty-text {
  margin: 0 0 8px;
  max-width: 320px;
  font-size: 1rem;
  line-height: 1.5;
  color: var(--ion-color-medium-shade, #5f6368);
}
.assistant-empty-shortcuts {
  display: grid;
  gap: 8px;
  width: 100%;
}
.assistant-shortcut {
  width: 100%;
  min-height: 40px;
  padding: 9px 14px;
  border: 1px solid var(--ion-border-color, #e3e5e8);
  border-radius: 10px;
  background: var(--ion-background-color, #fff);
  color: var(--ion-text-color, #1a1c20);
  font: inherit;
  font-size: 0.9rem;
  line-height: 1.35;
  text-align: start;
  cursor: pointer;
  overflow-wrap: anywhere;
}
.assistant-shortcut:hover,
.assistant-shortcut:focus-visible {
  border-color: var(--ion-color-primary);
  background: color-mix(in oklab, var(--ion-color-primary) 6%, transparent);
}
</style>
