<script setup lang="ts">
import { HubIcon } from '@erplora/ui/shell';
import { useId } from 'vue';

defineProps<{
  title: string;
  /** Beside the title, at the end of the button («Optional»). */
  hint?: string;
  /** `data-testid` of the section; its button is `<testid>-toggle`. */
  testid: string;
}>();
const open = defineModel<boolean>('open', { default: false });
const bodyId = useId();
</script>

<template>
  <section
    class="folded-section"
    :class="{ 'folded-section--open': open }"
    :data-testid="testid"
  >
    <button
      type="button"
      class="folded-section__toggle"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-controls="bodyId"
      :data-testid="`${testid}-toggle`"
      @click="open = !open"
    >
      <HubIcon
        class="folded-section__icon"
        :name="open ? 'ion:chevron-up-outline' : 'ion:chevron-down-outline'"
        aria-hidden="true"
      />
      <span class="folded-section__title">{{ title }}</span>
      <span
        v-if="hint"
        class="folded-section__hint"
      >{{ hint }}</span>
    </button>
    <div
      v-if="open"
      :id="bodyId"
      class="folded-section__body"
    >
      <slot />
    </div>
  </section>
</template>

<style scoped>
.folded-section {
  border: 1px solid var(--ep-border, #d9dde3);
  border-radius: var(--ep-radius-sm, 10px);
}
.folded-section__toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: var(--ep-touch-min, 48px);
  padding: 0 14px;
  border: 0;
  border-radius: inherit;
  background: transparent;
  color: var(--ion-text-color, #1d2025);
  font: inherit;
  font-weight: 600;
  text-align: start;
  cursor: pointer;
}
.folded-section__toggle:focus-visible {
  outline: none;
  box-shadow: var(--ep-focus-ring);
}
.folded-section__icon {
  flex: none;
  font-size: 18px;
  color: var(--ep-primary-text, #0b5f8a);
}
.folded-section__title {
  flex: 1 1 auto;
  min-width: 0;
}
.folded-section__hint {
  flex: none;
  font-size: 0.8rem;
  font-weight: 400;
  color: var(--ep-text-muted, #646b78);
}
.folded-section__body {
  padding: 0 14px 14px;
}
</style>
