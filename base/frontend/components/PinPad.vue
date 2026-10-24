<script setup lang="ts">
// The PIN pad (BASE-G54, G55, G60): as many circles as the business's PIN has digits (4 or 6), the keypad and the entry
// at the last digit, without a button (Clover's, hub#974; the old hub's LoginPage). The digits of a keyboard count
// too (a till with one), and Backspace erases. The arrow left of the 0 goes back (to the faces) where the screen
// offers it. The PIN never leaves this component but in `complete`, and its circles are emptied at once.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { HubIcon } from '@erplora/ui/shell';
import { useBaseI18n } from '../lib/i18n';

const props = withDefaults(
  defineProps<{
    /** Digits of the business's PIN. */
    length: number;
    /** What the pad asks («Enter your PIN», «PIN of Ana»): its accessible name. */
    label: string;
    /** Under the circles: what went wrong. */
    error?: string;
    /** While an entry is on its way: nothing is taken. */
    disabled?: boolean;
    /** The arrow left of the 0 (its accessible name); none: no arrow. */
    backLabel?: string;
  }>(),
  { error: '', disabled: false, backLabel: '' },
);

const emit = defineEmits<{ complete: [pin: string]; back: [] }>();

const { t } = useBaseI18n();
const digits = ref('');
const dots = computed(() => Array.from({ length: props.length }, (_, index) => index < digits.value.length));

function press(digit: string): void {
  if (props.disabled || digits.value.length >= props.length) return;
  digits.value += digit;
  if (digits.value.length < props.length) return;
  const pin = digits.value;
  digits.value = '';
  emit('complete', pin);
}

function erase(): void {
  if (props.disabled) return;
  digits.value = digits.value.slice(0, -1);
}

function onKey(event: KeyboardEvent): void {
  if (event.ctrlKey || event.metaKey || event.altKey || event.defaultPrevented) return;
  if (/^[0-9]$/.test(event.key)) press(event.key);
  else if (event.key === 'Backspace') erase();
}

onMounted(() => document.addEventListener('keydown', onKey));
onBeforeUnmount(() => document.removeEventListener('keydown', onKey));

defineExpose({ clear: () => (digits.value = '') });
</script>

<template>
  <div
    class="pinpad"
    role="group"
    data-testid="pinpad"
    :aria-label="label"
  >
    <div
      class="pinpad__dots"
      aria-hidden="true"
    >
      <span
        v-for="(on, index) in dots"
        :key="index"
        class="pinpad__dot"
        :class="{ 'is-filled': on }"
        data-testid="pinpad-dot"
      />
    </div>
    <p
      class="pinpad__error"
      role="alert"
      data-testid="pinpad-error"
    >
      {{ error }}
    </p>
    <div class="pinpad__keys">
      <button
        v-for="digit in ['1', '2', '3', '4', '5', '6', '7', '8', '9']"
        :key="digit"
        type="button"
        class="pinpad__key"
        :data-testid="`pinpad-key-${digit}`"
        :disabled="disabled"
        @click="press(digit)"
      >
        {{ digit }}
      </button>
      <button
        v-if="backLabel"
        type="button"
        class="pinpad__key pinpad__key--icon"
        data-testid="pinpad-back"
        :aria-label="backLabel"
        :title="backLabel"
        :disabled="disabled"
        @click="emit('back')"
      >
        <HubIcon
          name="ion:arrow-back-outline"
          aria-hidden="true"
        />
      </button>
      <span
        v-else
        aria-hidden="true"
      />
      <button
        type="button"
        class="pinpad__key"
        data-testid="pinpad-key-0"
        :disabled="disabled"
        @click="press('0')"
      >
        0
      </button>
      <button
        type="button"
        class="pinpad__key pinpad__key--icon"
        data-testid="pinpad-erase"
        :aria-label="t('base.pinpad.erase')"
        :title="t('base.pinpad.erase')"
        :disabled="disabled"
        @click="erase"
      >
        <HubIcon
          name="ion:backspace-outline"
          aria-hidden="true"
        />
      </button>
    </div>
  </div>
</template>

<style scoped>
.pinpad {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.pinpad__dots {
  display: flex;
  gap: 14px;
  padding: 8px 0;
}

.pinpad__dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 2px solid var(--ion-color-medium);
  transition: background-color 120ms ease;
}

.pinpad__dot.is-filled {
  background: var(--ion-color-primary);
  border-color: var(--ion-color-primary);
}

.pinpad__error {
  min-height: 1.25em;
  margin: 0;
  color: var(--ion-color-danger);
  font-size: 0.875rem;
  text-align: center;
}

.pinpad__keys {
  --pinpad-key: 72px;
  display: grid;
  grid-template-columns: repeat(3, var(--pinpad-key));
  gap: 12px;
}

.pinpad__key {
  width: var(--pinpad-key);
  height: var(--pinpad-key);
  border-radius: 50%;
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  background: var(--ion-card-background, var(--ion-background-color));
  color: var(--ion-text-color);
  font-size: 1.5rem;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.pinpad__key:active:not(:disabled) {
  background: var(--ion-color-step-100, #e6e6e6);
}

.pinpad__key:focus-visible {
  outline: 2px solid var(--ion-color-primary);
  outline-offset: 2px;
}

.pinpad__key:disabled {
  opacity: 0.5;
  cursor: default;
}

.pinpad__key--icon {
  font-size: 1.375rem;
}

/* A short screen (a low phone, 667 px tall; a laptop's browser): smaller keys, still well over a finger, so the whole
   pad fits under what is above it (the approval dialog's texts, the till's faces), never its last row cut off. */
@media (max-height: 740px) {
  .pinpad__keys {
    --pinpad-key: 56px;
  }
}
</style>
