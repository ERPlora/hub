<script setup lang="ts">
// The till's keypad: 3 columns, 1…9, the decimal key (in the reader's language), 0 and clear. It types
// an amount in major units with the dot («12.50»): never more decimals than allowed, never two
// separators nor leading zeros, never longer than `maxLength`. The sheet turns it into cents.
import { computed } from 'vue';

import { useLocale } from '../../composables/useT';

const props = withDefaults(defineProps<{ decimals?: number; maxLength?: number }>(), { decimals: 2, maxLength: 9 });
const value = defineModel<string>({ required: true });

const locale = useLocale();
const separator = computed(
  () => new Intl.NumberFormat(locale.value).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.',
);

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'dot', '0', 'clear'] as const;
type Key = (typeof KEYS)[number];

function press(key: Key): void {
  const now = value.value;
  if (key === 'clear') {
    value.value = '';
    return;
  }
  if (now.length >= props.maxLength) return;
  if (key === 'dot') {
    if (props.decimals > 0 && !now.includes('.')) value.value = `${now || '0'}.`;
    return;
  }
  const [, fraction] = now.split('.');
  if (fraction !== undefined && fraction.length >= props.decimals) return;
  value.value = now === '0' ? key : `${now}${key}`;
}

const label = (key: Key) => (key === 'dot' ? separator.value : key === 'clear' ? 'C' : key);
</script>

<template>
  <div class="pos-numpad">
    <button
      v-for="key in KEYS"
      :key="key"
      type="button"
      class="pos-numpad__key"
      :data-testid="`pos-key-${key}`"
      :aria-label="key === 'clear' ? $t('sale.pos.numpadClear') : undefined"
      :disabled="key === 'dot' && decimals === 0"
      @click="press(key)"
    >
      {{ label(key) }}
    </button>
  </div>
</template>

<style scoped>
.pos-numpad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.45rem;
  margin: 0.4rem 0;
}
.pos-numpad__key {
  min-height: 3.1rem;
  font: inherit;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-color-light, #f2f1ed));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
  cursor: pointer;
}
.pos-numpad__key:active {
  transform: scale(0.97);
}
.pos-numpad__key:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
