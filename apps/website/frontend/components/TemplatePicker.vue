<script setup lang="ts">
// TemplatePicker — the website's four designs as cards (Squarespace's and Wix's template pickers, reduced to
// four): each with a small drawing of its layout in the page's own colours, made of CSS boxes (no images), its name
// and a line on how it looks. A radio group: one is chosen; picking another emits it. Changing the design never
// touches the content (the server keeps both apart).
import { useT } from '../composables/useT';

import type { WebsiteTemplate } from '../operations';

const props = withDefaults(
  defineProps<{
    modelValue: WebsiteTemplate;
    /** The page's colours, to draw the thumbnails with. */
    primary: string;
    accent: string;
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [value: WebsiteTemplate] }>();

const t = useT();

const TEMPLATES: readonly WebsiteTemplate[] = ['classic', 'modern', 'minimal', 'bold'];

function pick(template: WebsiteTemplate): void {
  if (props.disabled || template === props.modelValue) return;
  emit('update:modelValue', template);
}
</script>

<template>
  <div
    class="wt-picker"
    role="radiogroup"
    :aria-label="t('website.template.heading')"
  >
    <button
      v-for="template in TEMPLATES"
      :key="template"
      type="button"
      role="radio"
      class="wt-card"
      :class="{ 'wt-card--chosen': template === modelValue }"
      :aria-checked="template === modelValue ? 'true' : 'false'"
      :disabled="disabled"
      :data-testid="`website-template-${template}`"
      @click="pick(template)"
    >
      <span
        class="wt-thumb"
        :class="`wt-thumb--${template}`"
        :style="{ '--wt-primary': primary, '--wt-accent': accent }"
        aria-hidden="true"
      >
        <span class="wt-bar" />
        <span class="wt-hero"><span class="wt-line wt-line--title" /><span class="wt-line" /><span class="wt-photo" /></span>
        <span class="wt-body"><span class="wt-block" /><span class="wt-block" /></span>
      </span>
      <span class="wt-name">{{ t(`website.template.${template}`) }}</span>
      <span class="wt-hint">{{ t(`website.template.${template}Hint`) }}</span>
    </button>
  </div>
</template>

<style scoped>
.wt-picker {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.wt-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  border: 2px solid var(--ion-color-step-150, #d9d9d9);
  border-radius: 12px;
  background: var(--ion-background-color, #fff);
  color: inherit;
  text-align: start;
  font: inherit;
  cursor: pointer;
}
.wt-card:disabled {
  cursor: default;
  opacity: 0.6;
}
.wt-card--chosen {
  border-color: var(--ion-color-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ion-color-primary) 25%, transparent);
}
.wt-card:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}
.wt-name {
  font-weight: 600;
}
.wt-hint {
  font-size: 0.8125rem;
  color: var(--ion-color-medium);
}
.wt-thumb {
  display: flex;
  flex-direction: column;
  gap: 4px;
  height: 92px;
  padding: 0 0 6px;
  overflow: hidden;
  border-radius: 6px;
  background: #fff;
  border: 1px solid #e5e7eb;
}
/* The bar: light with a line under it (bold's is dark), a dot of the main colour for «Log in». */
.wt-bar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  height: 10px;
  padding-inline: 6px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.wt-bar::after {
  content: '';
  width: 12px;
  height: 4px;
  border-radius: 2px;
  background: var(--wt-primary);
}
/* Classic: the header on a soft band of the main colour. */
.wt-thumb--classic .wt-hero {
  background: color-mix(in srgb, var(--wt-primary) 7%, #fff);
}
.wt-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 4px 8px;
}
.wt-line {
  display: block;
  width: 50%;
  height: 4px;
  border-radius: 2px;
  background: #9ca3af;
}
.wt-line--title {
  width: 70%;
  height: 6px;
  background: #374151;
}
.wt-photo {
  display: block;
  width: 80%;
  height: 16px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--wt-accent) 45%, #fff);
}
.wt-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 0 8px;
}
.wt-block {
  display: block;
  height: 8px;
  border-radius: 2px;
  background: #e5e7eb;
}
.wt-block:nth-child(2) {
  background: color-mix(in srgb, var(--wt-accent) 25%, #fff);
}
/* Modern: text and photo side by side, sections as cards. */
.wt-thumb--modern .wt-hero {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: auto auto;
  align-items: start;
  column-gap: 6px;
}
.wt-thumb--modern .wt-line,
.wt-thumb--modern .wt-line--title {
  width: 100%;
}
.wt-thumb--modern .wt-photo {
  grid-column: 2;
  grid-row: 1 / span 2;
  width: 100%;
  height: 22px;
}
.wt-thumb--modern .wt-body {
  flex-direction: row;
  background: #f3f4f6;
  padding: 4px 8px;
}
.wt-thumb--modern .wt-block {
  flex: 1;
  height: 14px;
  background: #fff;
  border-radius: 4px;
}
/* Minimal: a thin bar and one narrow column. */
.wt-thumb--minimal .wt-bar {
  height: 3px;
}
.wt-thumb--minimal .wt-hero {
  align-items: flex-start;
  padding: 8px 24px 2px;
}
.wt-thumb--minimal .wt-photo {
  display: none;
}
.wt-thumb--minimal .wt-body {
  padding: 0 24px;
}
.wt-thumb--minimal .wt-block {
  height: 2px;
  background: #d1d5db;
}
/* Bold: a dark bar and a big banner in the main colour. */
.wt-thumb--bold .wt-bar {
  background: #1f2328;
  border-bottom: 0;
}
.wt-thumb--bold .wt-hero {
  background: var(--wt-primary);
  padding: 8px;
}
.wt-thumb--bold .wt-line--title {
  height: 9px;
  background: #fff;
}
.wt-thumb--bold .wt-line {
  background: color-mix(in srgb, #fff 70%, var(--wt-primary));
}
.wt-thumb--bold .wt-photo {
  display: none;
}
.wt-thumb--bold .wt-block:nth-child(2) {
  height: 12px;
  background: var(--wt-accent);
}
</style>
