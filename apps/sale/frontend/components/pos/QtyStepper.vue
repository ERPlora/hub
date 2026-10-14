<script setup lang="ts">
// The quantity selector of a cart line: minus, the field and plus. It only says what was asked
// (`change`, as the server reads a decimal: «0.532»); the line keeps showing what the server keeps, so
// a refused quantity puts the field back by itself. Minus from one asks zero: the page removes the
// line. A product sold by weight or time types its quantity («0,532») and shows its unit. The signs are
// glyphs: `ion:remove-outline` is not registered yet (UI-REQUESTS.md, «POS»).
import { computed, useTemplateRef, watch } from 'vue';

import { useLocale } from '../../composables/useT';

const props = defineProps<{ quantity: string; unit: string; disabled?: boolean }>();
const emit = defineEmits<{ change: [quantity: string] }>();

const locale = useLocale();
const field = useTemplateRef<HTMLInputElement>('field');

const number = computed(() => new Intl.NumberFormat(locale.value, { maximumFractionDigits: 3, useGrouping: false }));
const shown = computed(() => number.value.format(Number(props.quantity)));
/** The locale's decimal separator, as typed («,» in Spanish). */
const separator = computed(() => number.value.formatToParts(1.5).find((part) => part.type === 'decimal')?.value ?? '.');

function reset(): void {
  if (field.value) field.value.value = shown.value;
}
watch(shown, reset);

const QUANTITY = /^\d+(?:\.\d{1,3})?$/;

function ask(next: number): void {
  emit('change', String(Math.round(next * 1000) / 1000));
}

function onChange(): void {
  const typed = (field.value?.value ?? '').trim().replace(separator.value, '.').replace(',', '.');
  if (!QUANTITY.test(typed) || Number(typed) === Number(props.quantity)) {
    reset();
    return;
  }
  ask(Number(typed));
}

const step = (by: number) => ask(Math.max(0, Number(props.quantity) + by));
</script>

<template>
  <span
    class="pos-qty"
    @click.stop
  >
    <button
      type="button"
      class="pos-qty__btn"
      data-testid="pos-qty-minus"
      :aria-label="$t('sale.pos.decrease')"
      :disabled="disabled"
      @click="step(-1)"
    >
      <span aria-hidden="true">−</span>
    </button>
    <input
      ref="field"
      class="pos-qty__field"
      type="text"
      inputmode="decimal"
      :value="shown"
      :aria-label="$t('sale.pos.quantity')"
      :disabled="disabled"
      @change="onChange"
      @keydown.enter="($event.target as HTMLInputElement).blur()"
    >
    <span
      v-if="unit !== 'ud'"
      class="pos-qty__unit"
      data-testid="pos-qty-unit"
    >{{ unit }}</span>
    <button
      type="button"
      class="pos-qty__btn"
      data-testid="pos-qty-plus"
      :aria-label="$t('sale.pos.increase')"
      :disabled="disabled"
      @click="step(1)"
    >
      <span aria-hidden="true">+</span>
    </button>
  </span>
</template>

<style scoped>
.pos-qty {
  display: inline-flex;
  align-items: center;
  overflow: hidden;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 10px;
}
.pos-qty__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  padding: 0;
  font-size: 1.15rem;
  font-weight: 700;
  color: var(--ion-text-color, #1c1b18);
  background: none;
  border: none;
  cursor: pointer;
}
.pos-qty__btn:disabled {
  opacity: 0.4;
  cursor: default;
}
.pos-qty__field {
  width: 2.3rem;
  height: 2rem;
  padding: 0;
  font: inherit;
  font-weight: 700;
  text-align: center;
  color: inherit;
  background: transparent;
  border: none;
  border-inline: 1px solid var(--ion-border-color, #e6e3db);
}
.pos-qty__unit {
  padding: 0 0.25rem;
  font-size: 0.72rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
