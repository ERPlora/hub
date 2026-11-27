<script setup lang="ts">
defineProps<{
  pressed: boolean;
  /** A dot in its corner (a time inside the minimum notice); the page says what it means. */
  marked?: boolean;
}>();
</script>

<template>
  <button
    type="button"
    class="choice-button"
    :class="{ 'choice-button--marked': marked }"
    :aria-pressed="pressed ? 'true' : 'false'"
  >
    <slot />
  </button>
</template>

<style scoped>
.choice-button {
  position: relative;
  min-width: 0;
  min-height: var(--ep-touch-min, 48px);
  padding: 0 6px;
  border: 1px solid var(--ep-border, #d9dde3);
  border-radius: var(--ep-radius-sm, 10px);
  background: var(--ep-surface-muted, #f5f6f8);
  color: var(--ion-text-color, #1d2025);
  font: inherit;
  font-size: 1rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: border-color 0.15s ease, background-color 0.15s ease;
}
.choice-button:hover:not(:disabled) {
  border-color: var(--ion-color-primary);
}
.choice-button:focus-visible {
  outline: none;
  border-color: var(--ion-color-primary);
  box-shadow: var(--ep-focus-ring);
}
.choice-button[aria-pressed='true'] {
  border-color: var(--ion-color-primary);
  background: var(--ion-color-primary);
  color: var(--ion-color-primary-contrast, #fff);
}
.choice-button:disabled {
  cursor: default;
  opacity: 0.5;
}
.choice-button--marked::after {
  content: '';
  position: absolute;
  top: 6px;
  right: 6px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ep-warning-text, #7a4f00);
}
.choice-button--marked[aria-pressed='true']::after {
  background: var(--ion-color-primary-contrast, #fff);
}
</style>
