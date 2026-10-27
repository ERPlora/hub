<script setup lang="ts">
// The till's product grid: a tile per product of the category in use, the «Open price» tile always
// last (SALE-F09; the same for everyone: whoever may not sell at an open price gets a manager's
// approval when the line is added), «Load more» while the server has more rows than the windows asked, «No products.» (or the
// reason the page passes) when there is nothing, and a spinner until the first answer. The grid
// scrolls inside its column, so the cart's footer never leaves the screen. The `lead` slot goes first in the
// grid (the menus of Menus in «All», SALE-F12).
import { HubIcon } from '@erplora/ui/shell';
import { IonSpinner } from '@ionic/vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';
import { useLocale } from '../../composables/useT';
import { currencySign, useBusinessMoney } from '../../lib/format';
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
    <button
      type="button"
      class="pos-open"
      data-testid="pos-open-price-tile"
      @click="emit('openPrice')"
    >
      <span
        class="pos-open__thumb"
        aria-hidden="true"
      >
        <HubIcon name="ion:pricetag-outline" />
      </span>
      <span class="pos-open__info">
        <span class="pos-tile__name">{{ $t('sale.pos.openPrice') }}</span>
        <span class="pos-tile__price">{{ $t('sale.pos.openPriceTag', { sign: currencySign(locale, business) || '¤' }) }}</span>
      </span>
    </button>
    <button
      v-if="hasMore"
      type="button"
      class="pos-grid__more"
      data-testid="pos-grid-more"
      @click="emit('loadMore')"
    >
      {{ $t('sale.pos.loadMore') }}
    </button>
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
  font: inherit;
  font-weight: 600;
  color: var(--ion-color-primary, #0091ce);
  background: transparent;
  border: 1px dashed var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: pointer;
}
.pos-open {
  display: flex;
  flex-direction: column;
  min-height: 8.4rem;
  margin: 0;
  padding: 0;
  overflow: hidden;
  font: inherit;
  text-align: left;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 14px;
  cursor: pointer;
}
.pos-open:hover {
  border-color: var(--ion-color-primary, #0091ce);
}
.pos-open:active {
  transform: scale(0.98);
}
.pos-open__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 4.85rem;
  font-size: 2rem;
  color: var(--ion-color-primary, #0091ce);
  background: color-mix(in srgb, var(--ion-color-primary, #0091ce) 12%, transparent);
}
.pos-open__info {
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
  padding: 0.5rem 0.6rem 0.65rem;
}
.pos-tile__name {
  overflow: hidden;
  font-size: 0.86rem;
  font-weight: 600;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pos-tile__price {
  align-self: flex-end;
  font-size: 0.9rem;
  font-weight: 800;
  color: var(--ion-color-primary, #0091ce);
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
  .pos-open {
    min-height: 8rem;
  }
}
@media (max-width: 340px) {
  .pos-grid {
    gap: 0.42rem;
  }
}
</style>
