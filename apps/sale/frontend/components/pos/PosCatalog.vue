<script setup lang="ts">
// The till's catalogue column (WORKBOOK «Vender»; SALE-F01 step 1, F07): the category strip with the
// magnifier and the ⋮ screen menu, the notices, and the grid. Everything comes from Inventory's own
// operations: the categories by name, the count of «All», and the articles of the category in use in
// windows of 100 (one subscription each; «Load more» opens the next). The search asks the server too.
// A sellable tap goes up (`add`); a blocked one says why, above the grid and in a toast, and adds
// nothing. Inventory off: the grid explains it and the open price stays. With products hidden by the
// till settings, only the open price is offered.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, toast } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import type { CategoryOut, ProductOut } from '../../../../inventory/frontend/operations';
import { useLiveWindows } from '../../composables/pos/useLiveWindows';
import { useT } from '../../composables/useT';
import CatalogNotices from './CatalogNotices.vue';
import CategoryStrip from './CategoryStrip.vue';
import ProductGrid from './ProductGrid.vue';
import ProductSearch from './ProductSearch.vue';
import ScreenMenu from './ScreenMenu.vue';

const props = defineProps<{
  /** The till settings' «Show products in the till». */
  showProducts: boolean;
  canOpenPrice: boolean;
  /** The till element the ⋮ menu puts on full screen. */
  target: HTMLElement | null;
}>();
const emit = defineEmits<{ add: [product: ProductOut]; openPrice: [] }>();

const t = useT();

const categoryId = shallowRef('');
const searching = shallowRef(false);
const tapNotice = shallowRef<string | null>(null);

const categories = useLiveWindows<'inventory.category.list', CategoryOut>('inventory.category.list', () => ({ sort: 'name' }), 100);
const allCount = useLive('inventory.product.list', { is_active: true, limit: 1, offset: 0 });
const products = useLiveWindows<'inventory.product.list', ProductOut>(
  'inventory.product.list',
  () => ({ is_active: true, sort: 'name', ...(categoryId.value ? { category_id: categoryId.value } : {}) }),
  100,
);

const shown = computed(() => (props.showProducts ? products.rows.value : []));
const inactive = computed(() => products.error.value?.code === 'app_inactive');
const failure = computed(() => {
  const error = products.error.value;
  if (!props.showProducts || !error || inactive.value) return null;
  return error.code === 'permission_denied' ? t('sale.live.noPermission') : t('sale.pos.catalogLoadFailed');
});
const emptyText = computed(() => {
  if (!props.showProducts) return undefined;
  if (inactive.value) return t('sale.pos.catalogAppInactive', { app: t('sale.pos.appInventory') });
  return failure.value ?? undefined;
});

function pick(product: ProductOut): void {
  searching.value = false;
  if (product.needs_tax_setup) {
    const reason = t('sale.pos.notSellableNoTaxCategory');
    tapNotice.value = reason;
    void toast(reason, 'warning');
    return;
  }
  tapNotice.value = null;
  emit('add', product);
}
</script>

<template>
  <section class="pos-catalog">
    <div class="pos-catalog__bar">
      <template v-if="showProducts">
        <CategoryStrip
          v-model="categoryId"
          :categories="categories.rows.value"
          :all-count="allCount.data.value?.total"
          :has-more="categories.hasMore.value"
          @load-more="categories.loadMore()"
        />
        <button
          type="button"
          class="pos-catalog__search"
          data-testid="pos-search-trigger"
          :aria-label="$t('sale.pos.search')"
          :title="$t('sale.pos.search')"
          :aria-pressed="searching ? 'true' : 'false'"
          @click="searching = !searching"
        >
          <HubIcon name="ion:search-outline" />
        </button>
      </template>
      <span
        v-else
        class="pos-catalog__spacer"
      />
      <ScreenMenu :target="target" />
    </div>
    <ProductSearch
      v-if="searching"
      @pick="pick"
      @close="searching = false"
    />
    <CatalogNotices :tap-notice="tapNotice" />
    <InlineFeedback
      v-if="failure"
      tone="danger"
      data-testid="pos-catalog-error"
    >
      {{ failure }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="pos-catalog-retry"
          @click="products.refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <ProductGrid
      :products="shown"
      :loading="showProducts && products.status.value === 'loading'"
      :has-more="showProducts && products.hasMore.value"
      :can-open-price="canOpenPrice"
      :empty-text="emptyText"
      @pick="pick"
      @open-price="emit('openPrice')"
      @load-more="products.loadMore()"
    />
    <slot />
  </section>
</template>

<style scoped>
.pos-catalog {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  padding: 0.72rem;
}
.pos-catalog__bar {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.68rem;
}
.pos-catalog__spacer {
  flex: 1;
}
.pos-catalog__search {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 3rem;
  height: 3.65rem;
  font-size: 1.25rem;
  color: var(--ion-color-primary, #0091ce);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  cursor: pointer;
}
.pos-catalog__search[aria-pressed='true'] {
  border-color: var(--ion-color-primary, #0091ce);
}
@media (max-width: 820px) {
  .pos-catalog {
    padding: 0.58rem;
  }
}
@media (max-width: 340px) {
  .pos-catalog {
    padding: 0.45rem;
  }
}
</style>
