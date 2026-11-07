<script setup lang="ts">
// The till's product grid: a tile per product of the category in use, the «Open price» tile always
// last (SALE-F09; the same for everyone: whoever may not sell at an open price gets a manager's
// approval when the line is added), «Load more» while the server has more rows than the windows asked, «No products.» (or the
// reason the page passes) when there is nothing, and a spinner until the first answer. The grid
// scrolls inside its column, so the cart's footer never leaves the screen. The `lead` slot goes first in the
// grid (the menus of Menus in «All», SALE-F12).
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';
import { useLocale } from '../../composables/useT';
import { currencySign, useBusinessMoney } from '../../lib/format';
import PosItemTile from './PosItemTile.vue';
import ProductTile from './ProductTile.vue';

defineProps<{
  products: readonly ProductOut[];
  loading?: boolean;
  hasMore?: boolean;
  /** Why there is no grid (Inventory not active, the catalogue did not load); «No products.» by default. */
  emptyText?: string;
}>();
const emit = defineEmits<{ pick: [product: ProductOut]; openPrice: []; loadMore: [] }>();

const locale = useLocale();
const business = useBusinessMoney();
</script>

<template>
  <div class="pos-grid">
    <slot name="lead" />
    <ProductTile
      v-for="item in products"
      :key="item.id"
      :product="item"
      @pick="emit('pick', $event)"
    />
    <div
      v-if="loading && !products.length"
      class="pos-grid__state"
      data-testid="pos-grid-loading"
    >
      <ion-spinner />
    </div>
    <p
      v-else-if="!products.length"
      class="pos-grid__state"
      role="status"
      data-testid="pos-grid-empty"
    >
      {{ emptyText ?? $t('sale.pos.noProducts') }}
    </p>
    <PosItemTile
      testid="pos-open-price-tile"
      :name="$t('sale.pos.openPrice')"
      :price="$t('sale.pos.openPriceTag', { sign: currencySign(locale, business) || '¤' })"
      icon="ion:pricetag-outline"
      @pick="emit('openPrice')"
    />
    <ion-button
      v-if="hasMore"
      fill="outline"
      class="pos-grid__more"
      data-testid="pos-grid-more"
      @click="emit('loadMore')"
    >
      <HubIcon
        slot="start"
        name="ion:chevron-down-outline"
      />
      {{ $t('sale.pos.loadMore') }}
    </ion-button>
  </div>
</template>

<style scoped>
.pos-grid {
  display: grid;
  flex: 1 1 auto;
  grid-template-columns: repeat(auto-fill, minmax(9.5rem, 1fr));
  align-content: start;
  gap: 0.62rem;
  min-height: 0;
  padding-bottom: 0.3rem;
  overflow: auto;
}
.pos-grid__state {
  grid-column: 1 / -1;
  max-width: 34rem;
  margin: 0 auto;
  padding: 2.5rem 1rem;
  line-height: 1.45;
  text-align: center;
  color: var(--ion-color-medium, #8b897f);
}
.pos-grid__more {
  grid-column: 1 / -1;
  min-height: 3rem;
  margin: 0;
  font-weight: 600;
  --border-style: dashed;
}
@media (min-width: 821px) and (max-width: 1100px) {
  .pos-grid {
    grid-template-columns: repeat(auto-fill, minmax(8.8rem, 1fr));
  }
}
@media (max-width: 820px) {
  .pos-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
    padding-bottom: 5.2rem;
  }
}
@media (max-width: 340px) {
  .pos-grid {
    gap: 0.42rem;
  }
}
</style>
