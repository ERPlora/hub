<script setup lang="ts">
import { computed, shallowRef, useId } from 'vue';

import { useBaseI18n } from '../lib/i18n';
import HelpMarkdown from './HelpMarkdown.vue';

const props = defineProps<{ text: string; name: 'purpose' | 'current' }>();
const emit = defineEmits<{ go: [path: string] }>();
const { t } = useBaseI18n();
const expanded = shallowRef(false);
const contentId = useId();
const firstParagraph = computed(() => props.text.trim().split(/\n\s*\n/, 1)[0]);
const collapsible = computed(() => firstParagraph.value.length > 280 || firstParagraph.value.length < props.text.trim().length);
const shownText = computed(() => (expanded.value ? props.text : firstParagraph.value));
const clamped = computed(() => !expanded.value && firstParagraph.value.length > 280);
</script>

<template>
  <div
    class="help-summary"
    :data-testid="`help-summary-${name}`"
  >
    <div
      :id="contentId"
      class="help-summary__content"
      :class="{ 'help-summary__content--clamped': clamped }"
      :data-testid="`help-summary-${name}-content`"
    >
      <HelpMarkdown
        :text="shownText"
        @go="emit('go', $event)"
      />
    </div>
    <button
      v-if="collapsible"
      type="button"
      class="help-summary__toggle"
      :data-testid="`help-summary-${name}-toggle`"
      :aria-expanded="expanded"
      :aria-controls="contentId"
      @click="expanded = !expanded"
    >
      {{ expanded ? t('base.help.less') : t('base.help.more') }}
    </button>
  </div>
</template>

<style scoped>
.help-summary__content--clamped :deep(.assistant-md) {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
}
.help-summary__toggle {
  min-height: 44px;
  margin: 4px 0 0 -8px;
  padding: 8px;
  border: 0;
  color: var(--ion-color-primary-shade);
  background: transparent;
  font: inherit;
  font-size: 0.8125rem;
  font-weight: 650;
  cursor: pointer;
}
:global(:root.ion-palette-dark) .help-summary__toggle {
  color: var(--ion-color-primary-tint);
}
.help-summary__toggle:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}
</style>
