<script setup lang="ts">
// The phone's cart button, at the bottom right of the catalogue (the grid keeps room for it): a round
// cart while the check is empty; with items, a pill with the total the server works out and a badge
// with how many. Its name says both («Open cart, 3 items, total €12.50»). It opens the cart drawer.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney } from '../../lib/format';

const props = defineProps<{ count: number; total: number | undefined; expanded: boolean }>();
const emit = defineEmits<{ open: [] }>();

const t = useT();
const locale = useLocale();

const totalText = computed(() => (props.total === undefined ? '—' : formatMoney(props.total, locale.value)));
const label = computed(() => {
  if (props.count === 0) return t('sale.pos.openCart');
  if (props.count === 1) return t('sale.pos.openCartWithItemsOne', { total: totalText.value });
  return t('sale.pos.openCartWithItems', { count: props.count, total: totalText.value });
});
</script>

<template>
  <button
    type="button"
    class="pos-fab"
    data-testid="pos-cart-fab"
    aria-controls="pos-cart-drawer"
    :aria-expanded="expanded ? 'true' : 'false'"
    :aria-label="label"
    :data-has-items="count > 0 ? 'true' : undefined"
    @click="emit('open')"
  >
    <HubIcon name="ion:cart-outline" />
    <template v-if="count > 0">
      <span
        class="pos-fab__total"
        data-testid="pos-cart-fab-total"
      >{{ totalText }}</span>
      <span
        class="pos-fab__count"
        data-testid="pos-cart-fab-count"
      >{{ count }}</span>
    </template>
  </button>
</template>

<style scoped>
.pos-fab {
  position: absolute;
  right: 1rem;
  bottom: 1rem;
  z-index: 10;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.45rem;
  min-width: 3.6rem;
  height: 3.6rem;
  margin: 0;
  padding: 0 1rem;
  font: inherit;
  font-size: 1.5rem;
  color: var(--ion-color-primary-contrast, #fff);
  background: var(--ion-color-primary, #0091ce);
  border: none;
  border-radius: 999px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  cursor: pointer;
}
.pos-fab__total {
  font-size: 1rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.pos-fab__count {
  position: absolute;
  top: -0.35rem;
  right: -0.25rem;
  min-width: 1.3rem;
  height: 1.3rem;
  padding: 0 0.3rem;
  font-size: 0.72rem;
  font-weight: 800;
  line-height: 1.3rem;
  color: var(--ion-color-primary, #0091ce);
  background: #fff;
  border: 1px solid var(--ion-color-primary, #0091ce);
  border-radius: 999px;
}
</style>
