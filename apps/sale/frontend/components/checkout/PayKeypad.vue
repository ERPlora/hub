<script setup lang="ts">
// The keypad of the charge sheet (the old `.numpad`): three columns, 1…9, the decimal separator, 0 and
// C. It only sends the key pressed ('.' for the separator, whatever the page language shows); what the
// keys build is the tender's (lib/checkout/tender.ts). No quick amounts: removed on purpose (2026-07-19).
import { computed } from 'vue';

import { useLocale } from '../../composables/useT';

const emit = defineEmits<{ key: [key: string] }>();

const locale = useLocale();

/** The separator a person of this language types: «.» in English, «,» in Spanish. */
const separator = computed(() => {
  try {
    return new Intl.NumberFormat(locale.value).formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.';
  } catch {
    return '.';
  }
});

const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '.', '0', 'C'] as const;
const KEY_ID: Record<string, string> = { '.': 'dot', C: 'clear' };
</script>

<template>
  <div
    class="pay-keypad"
    role="group"
    data-testid="sale-checkout-keypad"
    :aria-label="$t('sale.checkout.keypad')"
  >
    <button
      v-for="key in KEYS"
      :key="key"
      type="button"
      class="pay-keypad__key"
      :data-testid="`sale-checkout-keypad-${KEY_ID[key] ?? key}`"
      :aria-label="key === 'C' ? $t('sale.checkout.keypadClear') : undefined"
      @click="emit('key', key)"
    >
      {{ key === '.' ? separator : key }}
    </button>
  </div>
</template>

<style scoped>
.pay-keypad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.35rem;
  margin-bottom: 0.2rem;
}

.pay-keypad__key {
  min-height: var(--ep-touch-min, 48px);
  padding: 0.6rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: var(--ep-radius-sm, 10px);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  color: var(--ion-text-color, #1c1b18);
  font: inherit;
  font-size: 1.15rem;
  cursor: pointer;
}

.pay-keypad__key:active {
  background: var(--ion-color-light, #f2f1ed);
}

.pay-keypad__key:focus-visible {
  outline: 2px solid var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}
</style>
