<script setup lang="ts">
// The till's catalogue column (WORKBOOK «Vender»; SALE-F01 step 1, F07): the category strip with the
// magnifier and the ⋮ screen menu, the notices, and the grid. Everything comes from Inventory's own
// operations: the categories by name, the count of «All», and the articles of the category in use in
// windows of 100 (one subscription each; «Load more» opens the next). The search asks the server too.
// The grid and the search show what is sold out in Inventory too, greyed (SALE-F07), and the counts count
// what the grid shows (INVENTORY-F27). A sellable tap goes up (`add`); a blocked or sold-out one says why, above the
// grid and in a toast, and adds nothing. Inventory off: the grid explains it and the open price stays. With products hidden by the
// till settings, only the open price is offered. With the services of Services (SALE-F38,
// `showServices`), «Services» follows «All» in the strip and shows their grid (first, when products are
// hidden; «All» keeps the open price); a sellable service goes up (`service`), the search finds them too.
// With the menus of Menus (SALE-F12, `showCombos`), «All» shows them first in the grid; a tap goes up (`combo`).
// With VeriFactu on and readable (`fiscal`), its notice goes first when it refuses new sales now (SALE-F07).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { HubIcon, toast } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import type { SaleComboOut } from '../../../../combo/frontend/operations';
import type { CategoryOut, ProductOut } from '../../../../inventory/frontend/operations';
import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useLiveWindows } from '../../composables/useLiveWindows';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useT } from '../../composables/useT';
import CatalogNotices from './CatalogNotices.vue';
import CategoryStrip from './CategoryStrip.vue';
import FiscalNotice from './FiscalNotice.vue';
import ComboTiles from './ComboTiles.vue';
import ProductGrid from './ProductGrid.vue';
import ProductSearch from './ProductSearch.vue';
import ScreenMenu from './ScreenMenu.vue';
import ServiceGrid from './ServiceGrid.vue';
import { SERVICES } from './till';

const props = withDefaults(
  defineProps<{
    /** The till settings' «Show products in the till». */
    showProducts: boolean;
    canOpenPrice: boolean;
    /** «Show services in the till», with Services on and readable (SALE-F38). */
    showServices?: boolean;
    /** Menus on and readable (SALE-F12). */
    showCombos?: boolean;
    /** VeriFactu on and readable (SALE-F07). */
    fiscal?: boolean;
  }>(),
  { showServices: false, showCombos: false, fiscal: false },
);
const emit = defineEmits<{
  add: [product: ProductOut];
  service: [service: ServiceSaleOut];
  combo: [combo: SaleComboOut];
  openPrice: [];
}>();

const t = useT();
const taxName = useTaxName();

const categoryId = shallowRef('');
const servicesCount = shallowRef<number | undefined>(undefined);
/** With products hidden, the services come first. */
watch(
  () => [props.showProducts, props.showServices],
  () => {
    if (props.showServices && !props.showProducts) categoryId.value = SERVICES;
    else if (!props.showServices && categoryId.value === SERVICES) categoryId.value = '';
  },
  { immediate: true },
);
const servicesMode = computed(() => props.showServices && categoryId.value === SERVICES);
/** The product grid's category: «All» while the services are on show. */
const productCategory = computed(() => (categoryId.value === SERVICES ? '' : categoryId.value));
const searching = shallowRef(false);
const tapNotice = shallowRef<string | null>(null);

const categories = useLiveWindows<'inventory.category.list', CategoryOut>('inventory.category.list', () => ({ sort: 'name' }), 100);
const allCount = useLive('inventory.product.list', { is_active: true, include_sold_out: true, limit: 1, offset: 0 });
const products = useLiveWindows<'inventory.product.list', ProductOut>(
  'inventory.product.list',
  () => ({
    is_active: true,
    include_sold_out: true,
    sort: 'name',
    ...(productCategory.value ? { category_id: productCategory.value } : {}),
  }),
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

/** A tap on something the till cannot sell now: the reason above the grid and in a toast; nothing is added. */
function refuse(reason: string): void {
  tapNotice.value = reason;
  void toast(reason, 'warning');
}

/** A tap on something without VAT. */
function blocked(): void {
  refuse(t('sale.pos.notSellableNoTaxCategory', { tax: taxName.value }));
}

function pick(product: ProductOut): void {
  searching.value = false;
  if (product.is_sold_out) return refuse(t('sale.pos.soldOut', { name: product.name }));
  if (product.needs_tax_setup) return blocked();
  tapNotice.value = null;
  emit('add', product);
}

function pickService(service: ServiceSaleOut): void {
  searching.value = false;
  if (service.needs_tax_setup) return blocked();
  tapNotice.value = null;
  emit('service', service);
}
</script>

<template>
  <section class="pos-catalog">
    <div class="pos-catalog__bar">
      <template v-if="showProducts || showServices">
        <CategoryStrip
          v-model="categoryId"
          :categories="showProducts ? categories.rows.value : []"
          :all-count="showProducts ? allCount.data.value?.total : undefined"
          :has-more="showProducts && categories.hasMore.value"
          :with-services="showServices"
          :services-count="servicesCount"
          @load-more="categories.loadMore()"
        />
        <button
          v-if="showProducts"
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
      <ScreenMenu />
    </div>
    <ProductSearch
      v-if="searching"
      :with-services="showServices"
      @pick="pick"
      @pick-service="pickService"
      @close="searching = false"
    />
    <FiscalNotice v-if="fiscal" />
    <CatalogNotices :tap-notice="tapNotice" />
    <InlineFeedback
      v-if="failure && !servicesMode"
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
    <ServiceGrid
      v-if="showServices"
      v-show="servicesMode"
      @pick="pickService"
      @total="servicesCount = $event"
    />
    <ProductGrid
      v-if="!servicesMode"
      :products="shown"
      :loading="showProducts && products.status.value === 'loading'"
      :has-more="showProducts && products.hasMore.value"
      :can-open-price="canOpenPrice"
      :empty-text="emptyText"
      @pick="pick"
      @open-price="emit('openPrice')"
      @load-more="products.loadMore()"
    >
      <template
        v-if="showCombos && !productCategory"
        #lead
      >
        <ComboTiles @pick="emit('combo', $event)" />
      </template>
    </ProductGrid>
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
