<script setup lang="ts">
// PalettePicker — the website's palettes as swatch cards (Squarespace's colour palettes, Wix's site themes and
// Shopify's colour schemes, reduced to a short curated list): the eight of apps/website/palettes.json. Each card shows
// its main and second colour on the light page and on the dark one, and its name. A radio group: one is chosen,
// highlighted; picking another emits it and drops the owner's colours (`custom` → null), so the new palette shows as
// it is. Under the cards, the two colours on show (the owner's, or the chosen palette's own) as colour fields:
// changing one emits the owner's pair over the palette (`update:custom`), and «Reset colours», shown only then,
// gives the palette's own back.
import { ColorInput } from '@erplora/ui/components';
import { IonButton, IonItem, IonList, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import { CURATED, currentColours, PALETTE_IDS, withColour } from '../lib/palettes';
import type { CustomColours, PaletteId } from '../operations';

const props = withDefaults(
  defineProps<{
    modelValue: PaletteId;
    /** The owner's two colours over the palette's (`v-model:custom`); null = the palette's own. */
    custom?: CustomColours | null;
    disabled?: boolean;
  }>(),
  { custom: null, disabled: false },
);

const emit = defineEmits<{
  'update:modelValue': [value: PaletteId];
  'update:custom': [value: CustomColours | null];
}>();

const t = useT();

/** The two colours in the fields. */
const shown = computed(() => currentColours({ palette: props.modelValue, custom: props.custom }));

function swatch(id: PaletteId): Record<string, string> {
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
  if (props.custom) emit('update:custom', null);
}

function change(key: keyof CustomColours, value: string): void {
  if (props.disabled) return;
  emit('update:custom', withColour({ palette: props.modelValue, custom: props.custom }, key, value));
}

function reset(): void {
  if (!props.disabled) emit('update:custom', null);
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
        :style="swatch(id)"
        aria-hidden="true"
      >
        <span class="wp-half wp-half--light"><span class="wp-dot wp-dot--primary" /><span class="wp-dot wp-dot--accent" /></span>
        <span class="wp-half wp-half--dark"><span class="wp-dot wp-dot--dark-primary" /><span class="wp-dot wp-dot--accent" /></span>
      </span>
      <span class="wp-name">{{ t(`website.palette.${id}`) }}</span>
    </button>
  </div>
  <ion-list
    inset
    class="wp-colours"
  >
    <ColorInput
      :model-value="shown.primary"
      :label="t('website.colours.primary')"
      :disabled="disabled"
      testid="website-colour-primary"
      @update:model-value="change('primary', $event)"
    />
    <ColorInput
      :model-value="shown.accent"
      :label="t('website.colours.accent')"
      :disabled="disabled"
      testid="website-colour-accent"
      @update:model-value="change('accent', $event)"
    />
    <ion-item lines="none">
      <ion-note class="wp-note">
        {{ t('website.palette.hint') }}
      </ion-note>
    </ion-item>
    <ion-item
      v-if="custom && !disabled"
      lines="none"
    >
      <ion-button
        fill="clear"
        size="small"
        data-testid="website-colours-reset"
        @click="reset"
      >
        {{ t('website.palette.reset') }}
      </ion-button>
    </ion-item>
  </ion-list>
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
.wp-note {
  font-size: 0.8125rem;
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
