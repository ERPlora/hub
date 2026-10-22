<script setup lang="ts">
// PalettePicker — the website's palettes as swatch cards (Squarespace's colour palettes, Wix's site themes and
// Shopify's colour schemes, reduced to a short curated list): the eight of apps/website/palettes.json and «Your
// colours». Each card shows its main and second colour on the light page and on the dark one, and its name. A radio
// group: one is chosen, highlighted; picking another emits it. The page shows the two colour fields of «Your colours».
import { useT } from '../composables/useT';
import { CURATED, PALETTE_IDS } from '../lib/palettes';
import type { CustomColours, PaletteId } from '../operations';

const props = withDefaults(
  defineProps<{
    modelValue: PaletteId;
    /** The owner's colours, drawn on «Your colours» once chosen. */
    custom: CustomColours | null;
    disabled?: boolean;
  }>(),
  { disabled: false },
);

const emit = defineEmits<{ 'update:modelValue': [value: PaletteId] }>();

const t = useT();

/** «Your colours» before any is chosen: a neutral pair. */
const UNSET = { primary: '#6b7280', accent: '#d1d5db' };

function swatch(id: PaletteId): Record<string, string> {
  if (id === 'custom') {
    const { primary, accent } = props.custom ?? UNSET;
    return { '--wp-primary': primary, '--wp-accent': accent, '--wp-bg': '#ffffff', '--wp-dark-bg': '#121417', '--wp-dark-primary': primary };
  }
  const palette = CURATED[id];
  return {
    '--wp-primary': palette.light.primary,
    '--wp-accent': palette.accent,
    '--wp-bg': palette.light.bg,
    '--wp-dark-bg': palette.dark.bg,
    '--wp-dark-primary': palette.dark.primary,
  };
}

function pick(id: PaletteId): void {
  if (props.disabled || id === props.modelValue) return;
  emit('update:modelValue', id);
}
</script>

<template>
  <div
    class="wp-picker"
    role="radiogroup"
    :aria-label="t('website.palette.label')"
  >
    <button
      v-for="id in PALETTE_IDS"
      :key="id"
      type="button"
      role="radio"
      class="wp-card"
      :class="{ 'wp-card--chosen': id === modelValue }"
      :aria-checked="id === modelValue ? 'true' : 'false'"
      :disabled="disabled"
      :data-testid="`website-palette-${id}`"
      @click="pick(id)"
    >
      <span
        class="wp-swatch"
        :class="{ 'wp-swatch--custom': id === 'custom' && !custom }"
        :style="swatch(id)"
        aria-hidden="true"
      >
        <span class="wp-half wp-half--light"><span class="wp-dot wp-dot--primary" /><span class="wp-dot wp-dot--accent" /></span>
        <span class="wp-half wp-half--dark"><span class="wp-dot wp-dot--dark-primary" /><span class="wp-dot wp-dot--accent" /></span>
      </span>
      <span class="wp-name">{{ t(`website.palette.${id}`) }}</span>
    </button>
  </div>
</template>

<style scoped>
.wp-picker {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.wp-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px;
  border: 2px solid var(--ion-color-step-150, #d9d9d9);
  border-radius: 12px;
  background: var(--ion-background-color, #fff);
  color: inherit;
  text-align: start;
  font: inherit;
  cursor: pointer;
}
.wp-card:disabled {
  cursor: default;
  opacity: 0.6;
}
.wp-card--chosen {
  border-color: var(--ion-color-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--ion-color-primary) 25%, transparent);
}
.wp-card:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}
.wp-swatch {
  display: grid;
  grid-template-columns: 1fr 1fr;
  height: 40px;
  overflow: hidden;
  border-radius: 8px;
  border: 1px solid rgb(0 0 0 / 0.08);
}
.wp-half {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
}
.wp-half--light {
  background: var(--wp-bg);
}
.wp-half--dark {
  background: var(--wp-dark-bg);
}
.wp-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  box-shadow: 0 0 0 1px rgb(0 0 0 / 0.1);
}
.wp-dot--primary {
  background: var(--wp-primary);
}
.wp-dot--dark-primary {
  background: var(--wp-dark-primary);
}
.wp-dot--accent {
  background: var(--wp-accent);
}
.wp-swatch--custom .wp-dot {
  background: conic-gradient(#ef4444, #f59e0b, #22c55e, #3b82f6, #a855f7, #ef4444);
}
.wp-name {
  font-size: 0.875rem;
  font-weight: 600;
}
@media (max-width: 360px) {
  .wp-picker {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
