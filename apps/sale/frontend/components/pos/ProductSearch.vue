<script setup lang="ts">
// The till's product search: a floating, translucent panel over the grid (it does not push it), with
// «Search product…» and the live answer of Inventory for what is typed — by name or SKU, across the
// whole catalogue (sold out too, SALE-F07), 20 at a time. A row shows the name, the SKU (or «Sold out», or
// why it cannot be sold) and the price; a tap hands the product up, where the same rules as a tile apply. With the services of Services
// (SALE-F38, `withServices`), the services it finds come after them (`pickService`). Mounted only while
// open. A row's tap and its aria-disabled live on a native button inside the ion-item: an ion-item rewrites
// its own aria-disabled from its `disabled`, which would swallow the tap.
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonItem, IonList, IonSearchbar, IonSpinner } from '@ionic/vue';
import { computed, onMounted, shallowRef, useTemplateRef } from 'vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';
import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney } from '../../lib/format';
import ServiceSearchResults from './ServiceSearchResults.vue';

withDefaults(defineProps<{ withServices?: boolean }>(), { withServices: false });
const emit = defineEmits<{ pick: [product: ProductOut]; pickService: [service: ServiceSaleOut]; close: [] }>();

const t = useT();
const locale = useLocale();
const taxName = useTaxName();
const term = shallowRef('');
const { data, status, error } = useLive('inventory.product.list', () => ({
  search: term.value,
  is_active: true,
  include_sold_out: true,
  sort: 'name' as const,
  limit: 20,
  offset: 0,
}));

const rows = computed(() => data.value?.rows ?? []);

/** Under the name: «Sold out», why it cannot be sold, or its SKU. */
function note(item: ProductOut): string {
  if (item.is_sold_out) return t('sale.pos.soldOutBadge');
  return item.needs_tax_setup ? t('sale.pos.notSellableNoTaxCategory', { tax: taxName.value }) : item.sku;
}

function onInput(event: CustomEvent<{ value?: string | null }>): void {
  term.value = (event.detail.value ?? '').trim();
}

const bar = useTemplateRef<{ $el: HTMLElement & { setFocus?: () => Promise<void> } }>('bar');
onMounted(() => void bar.value?.$el.setFocus?.());
</script>

<template>
  <div
    class="pos-search"
    role="dialog"
    :aria-label="$t('sale.pos.search')"
    data-testid="pos-search"
    @keydown.esc="emit('close')"
  >
    <div class="pos-search__bar">
      <ion-searchbar
        ref="bar"
        :placeholder="$t('sale.pos.searchPlaceholder')"
        :debounce="250"
        :maxlength="200"
        @ion-input="onInput"
      />
      <ion-button
        fill="clear"
        :aria-label="$t('sale.pos.searchClose')"
        data-testid="pos-search-close"
        @click="emit('close')"
      >
        <HubIcon
          slot="icon-only"
          name="ion:close-outline"
        />
      </ion-button>
    </div>
    <div
      v-if="status === 'loading' && !rows.length"
      class="pos-search__state"
    >
      <ion-spinner />
    </div>
    <p
      v-else-if="error"
      class="pos-search__state pos-search__state--error"
      role="alert"
      data-testid="pos-search-error"
    >
      {{ error.message }}
    </p>
    <p
      v-else-if="!rows.length"
      class="pos-search__state"
      data-testid="pos-search-empty"
    >
      {{ $t('sale.pos.noProducts') }}
    </p>
    <ion-list
      v-else
      class="pos-search__list"
    >
      <ion-item
        v-for="item in rows"
        :key="item.id"
      >
        <button
          type="button"
          class="pos-search__row"
          :data-testid="`pos-search-${item.id}`"
          :aria-disabled="item.is_sold_out || item.needs_tax_setup ? 'true' : undefined"
          @click="emit('pick', item)"
        >
          <span class="pos-search__text">
            <span class="pos-search__name">{{ item.name }}</span>
            <span
              class="pos-search__note"
              :class="{ 'pos-search__warn': item.is_sold_out || item.needs_tax_setup }"
            >{{ note(item) }}</span>
          </span>
          <span class="pos-search__price">{{ formatMoney(item.price, locale) }}</span>
        </button>
      </ion-item>
    </ion-list>
    <ServiceSearchResults
      v-if="withServices"
      :term="term"
      @pick="emit('pickService', $event)"
    />
  </div>
</template>

<style scoped>
.pos-search {
  position: absolute;
  inset: 0.5rem 0.5rem auto;
  z-index: 20;
  display: flex;
  flex-direction: column;
  max-height: calc(100% - 1rem);
  padding: 0.4rem;
  background: color-mix(in srgb, var(--ion-background-color, #fff) 92%, transparent);
  backdrop-filter: blur(10px);
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 14px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, 0.25);
}
.pos-search__bar {
  display: flex;
  align-items: center;
}
.pos-search__list {
  overflow-y: auto;
  background: transparent;
}
.pos-search__list ion-item {
  --background: transparent;
  --padding-start: 0;
  --padding-top: 0;
  --padding-bottom: 0;
  --inner-padding-end: 0;
  border-radius: 10px;
}
.pos-search__row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  min-height: 2.75rem;
  margin: 0;
  padding: 0.625rem 1rem;
  font: inherit;
  text-align: left;
  color: inherit;
  background: none;
  border: 0;
  border-radius: 10px;
  cursor: pointer;
}
.pos-search__row:active {
  background: var(--ion-color-step-100, rgba(0, 0, 0, 0.06));
}
.pos-search__row[aria-disabled='true'] {
  opacity: 0.8;
  cursor: not-allowed;
}
.pos-search__text {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 0.125rem;
  min-width: 0;
  line-height: 1.25;
}
.pos-search__name {
  overflow: hidden;
  font-size: 1rem;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pos-search__note {
  font-size: 0.875rem;
  color: var(--ion-color-step-600, #666);
}
.pos-search__price {
  flex: none;
  font-size: 0.95rem;
  font-weight: 800;
  color: var(--ion-color-primary, #0091ce);
}
.pos-search__warn {
  white-space: normal;
  color: var(--ion-color-warning-shade, #b26a00);
}
.pos-search__state {
  margin: 0;
  padding: 1.2rem 1rem;
  text-align: center;
  color: var(--ion-color-medium, #8b897f);
}
.pos-search__state--error {
  color: var(--ion-color-danger, #d9480f);
}
</style>
