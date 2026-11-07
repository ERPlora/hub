<script setup lang="ts">
// The phone's cart button, at the bottom right of the catalogue (the grid keeps room for it): a round
// cart while the check is empty; with items, a pill with the total the server works out and a badge
// with how many. Its name says both («Open cart, 3 items, total €12.50»). It opens the cart drawer.
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonFab, IonFabButton } from '@ionic/vue';
import { computed } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';

const props = defineProps<{ count: number; total: number | undefined; expanded: boolean }>();
const emit = defineEmits<{ open: [] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const totalText = computed(() => (props.total === undefined ? '—' : formatMoney(props.total, locale.value, business.value)));
const label = computed(() => {
  if (props.count === 0) return t('sale.pos.openCart');
  if (props.count === 1) return t('sale.pos.openCartWithItemsOne', { total: totalText.value });
  return t('sale.pos.openCartWithItems', { count: props.count, total: totalText.value });
});
</script>

<template>
  <ion-fab
    class="pos-fab"
    horizontal="end"
    vertical="bottom"
  >
    <ion-fab-button
      class="pos-fab__button"
      :style="{ width: count > 0 ? 'max-content' : undefined, minWidth: count > 0 ? '8rem' : undefined }"
      data-testid="pos-cart-fab"
      aria-controls="pos-cart-drawer"
      :aria-expanded="expanded ? 'true' : 'false'"
      :aria-label="label"
      :data-has-items="count > 0 ? 'true' : undefined"
      @click="emit('open')"
    >
      <HubIcon
        class="pos-fab__icon"
        name="ion:cart-outline"
        aria-hidden="true"
      />
      <span
        v-if="count > 0"
        class="pos-fab__total"
        data-testid="pos-cart-fab-total"
      >{{ totalText }}</span>
      <ion-badge
        v-if="count > 0"
        class="pos-fab__count"
        data-testid="pos-cart-fab-count"
      >
        {{ count }}
      </ion-badge>
    </ion-fab-button>
  </ion-fab>
</template>

<style scoped>
.pos-fab {
  position: absolute;
  right: 1rem;
  bottom: 1rem;
  z-index: 10;
  display: block;
  margin: 0;
}
.pos-fab__button {
  width: max-content !important;
  min-width: 3.6rem;
  height: 3.6rem;
  margin: 0;
  font-size: 1.5rem;
  --border-radius: 999px;
  --box-shadow: var(--ep-shadow-pop);
  --overflow: visible;
}
.pos-fab__button::part(native) {
  display: inline-flex;
  gap: 0.45rem;
  width: max-content !important;
  min-width: 3.6rem;
  padding: 0 1rem;
}
.pos-fab__icon {
  flex: none;
  width: 1.5rem;
  height: 1.5rem;
  font-size: 1.5rem;
  color: var(--ion-color-primary-contrast);
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
  z-index: 1;
  display: grid;
  place-items: center;
  min-width: 1.3rem;
  height: 1.3rem;
  padding: 0 0.3rem;
  font-size: 0.72rem;
  line-height: 1.3rem;
  color: var(--ion-color-primary);
  background: var(--ion-card-background);
  border: 1px solid var(--ion-color-primary);
}
</style>
