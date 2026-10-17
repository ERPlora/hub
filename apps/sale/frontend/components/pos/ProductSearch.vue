<script setup lang="ts">
// The till's product search: a floating, translucent panel over the grid (it does not push it), with
// «Search product…» and the live answer of Inventory for what is typed — by name or SKU, across the
// whole catalogue, 20 at a time. A row shows the name, the SKU (or why it cannot be sold) and the
// price; a tap hands the product up, where the same rules as a tile apply. With the services of Services
// (SALE-F38, `withServices`), the services it finds come after them (`pickService`). Mounted only while
// open.
import { useLive } from '@erplora/ui/sdk';
import { HubIcon } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonNote, IonSearchbar, IonSpinner } from '@ionic/vue';
import { computed, onMounted, shallowRef, useTemplateRef } from 'vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';
import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale } from '../../composables/useT';
import { formatMoney } from '../../lib/format';
import ServiceSearchResults from './ServiceSearchResults.vue';

withDefaults(defineProps<{ withServices?: boolean }>(), { withServices: false });
const emit = defineEmits<{ pick: [product: ProductOut]; pickService: [service: ServiceSaleOut]; close: [] }>();

const locale = useLocale();
const taxName = useTaxName();
const term = shallowRef('');
const { data, status, error } = useLive('inventory.product.list', () => ({
  search: term.value,
  is_active: true,
  sort: 'name' as const,
  limit: 20,
  offset: 0,
}));

const rows = computed(() => data.value?.rows ?? []);

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
        button
        :detail="false"
        :data-testid="`pos-search-${item.id}`"
        :aria-disabled="item.needs_tax_setup ? 'true' : undefined"
        @click="emit('pick', item)"
      >
        <ion-label>
          <h3>{{ item.name }}</h3>
          <p :class="{ 'pos-search__warn': item.needs_tax_setup }">
            {{ item.needs_tax_setup ? $t('sale.pos.notSellableNoTaxCategory', { tax: taxName }) : item.sku }}
          </p>
        </ion-label>
        <ion-note
          slot="end"
          class="pos-search__price"
        >
          {{ formatMoney(item.price, locale) }}
        </ion-note>
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
  border-radius: 10px;
}
.pos-search__list ion-item[aria-disabled='true'] {
  opacity: 0.8;
}
.pos-search__price {
  font-size: 0.95rem;
  font-weight: 800;
  --color: var(--ion-color-primary, #0091ce);
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
