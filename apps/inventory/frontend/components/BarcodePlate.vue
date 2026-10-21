<script setup lang="ts">
// INVENTORY-F25 (WORKBOOK «Ficha del producto»): the SKU's Code 128 on a white plate with the SKU under it.
// Always black on white, whatever the theme, so a scanner reads it (inventory#45). `svg` is exposed for the
// browser's print dialog (lib/print-label.ts).
import { computed, ref } from 'vue';

import { useT } from '../composables/useT';
import { code128 } from '../lib/barcode';

const props = defineProps<{ value: string }>();
const { t } = useT();

/** Modules of white on each side: the quiet zone a scanner needs. */
const QUIET = 10;
const HEIGHT = 50;

const code = computed(() => code128(props.value));
const svg = ref<SVGSVGElement | null>(null);
defineExpose({ svg });
</script>

<template>
  <div
    class="barcode-plate"
    data-testid="inventory-barcode"
  >
    <template v-if="code">
      <svg
        ref="svg"
        role="img"
        :aria-label="t('inventory.barcode.label', { sku: value })"
        :viewBox="`0 0 ${code.modules + QUIET * 2} ${HEIGHT}`"
        preserveAspectRatio="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <rect
          class="background"
          x="0"
          y="0"
          :width="code.modules + QUIET * 2"
          :height="HEIGHT"
          fill="#ffffff"
        />
        <rect
          v-for="bar in code.bars"
          :key="bar.x"
          class="bar"
          :x="bar.x + QUIET"
          y="0"
          :width="bar.width"
          :height="HEIGHT"
          fill="#000000"
        />
      </svg>
      <div
        class="barcode-text"
        data-testid="inventory-barcode-text"
      >
        {{ value }}
      </div>
    </template>
    <p
      v-else
      class="barcode-invalid"
      data-testid="inventory-barcode-invalid"
    >
      {{ t('inventory.barcode.invalid') }}
    </p>
  </div>
</template>

<style scoped>
.barcode-plate {
  margin: 12px 16px;
  padding: 12px 16px 8px;
  border-radius: 8px;
  border: 1px solid var(--ion-color-step-150, #d7d8da);
  background: #ffffff;
  color: #000000;
  text-align: center;
}

.barcode-plate svg {
  display: block;
  width: 100%;
  max-width: 320px;
  height: 64px;
  margin: 0 auto;
}

.barcode-text {
  margin-top: 6px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 14px;
  letter-spacing: 0.08em;
  overflow-wrap: anywhere;
}

.barcode-invalid {
  margin: 0;
  font-size: 14px;
}
</style>
