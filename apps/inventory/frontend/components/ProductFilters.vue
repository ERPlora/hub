<script lang="ts">
import type { InputOf } from '@erplora/ui/sdk';

import { parseMoney } from '../lib/money';
import { readQuantity } from '../lib/quantity';

/** The filters as typed; a filter not in use is absent. */
export interface ProductFilterValues {
  name?: string;
  sku?: string;
  priceMin?: string;
  priceMax?: string;
  stockMin?: string;
  stockMax?: string;
}

/** The filters as `inventory.product.list` takes them: cents and exact quantities. */
export function filterParams(values: ProductFilterValues): Partial<InputOf<'inventory.product.list'>> {
  const cents = (text?: string) => {
    const read = parseMoney(text ?? '');
    return read.ok && read.cents !== null ? read.cents : undefined;
  };
  const quantity = (text?: string) => {
    const read = readQuantity(text ?? '');
    return read.ok && read.value !== null ? read.value : undefined;
  };
  const out: Partial<InputOf<'inventory.product.list'>> = {
    name: values.name || undefined,
    sku: values.sku || undefined,
    price_min: cents(values.priceMin),
    price_max: cents(values.priceMax),
    stock_min: quantity(values.stockMin),
    stock_max: quantity(values.stockMax),
  };
  return Object.fromEntries(Object.entries(out).filter(([, value]) => value !== undefined));
}
</script>

<script setup lang="ts">
// The column filters of Products (WORKBOOK «Productos»: name, SKU, price from/to, stock from/to), the
// old table's funnel with the count of filters in use, opening a dialog. «Apply filters» hands them to
// the page; an amount or a quantity that cannot be read is not applied (it says so under its field);
// «Clear filters» drops them all. A stand-in until DataTable has column filters (UI-REQUESTS.md).
import { FormModal } from '@erplora/ui/components';
import { HubIcon } from '@erplora/ui/shell';
import { IonBadge, IonButton, IonInput } from '@ionic/vue';
import { computed, ref } from 'vue';

import MoneyInput from './MoneyInput.vue';
import QuantityInput from './QuantityInput.vue';

const values = defineModel<ProductFilterValues>({ required: true });

const open = ref(false);
const draft = ref<Required<ProductFilterValues>>({ name: '', sku: '', priceMin: '', priceMax: '', stockMin: '', stockMax: '' });
const tried = ref(false);

const count = computed(() => {
  const v = values.value;
  return [v.name, v.sku, v.priceMin || v.priceMax, v.stockMin || v.stockMax].filter(Boolean).length;
});

function show(): void {
  draft.value = { name: '', sku: '', priceMin: '', priceMax: '', stockMin: '', stockMax: '', ...values.value };
  tried.value = false;
  open.value = true;
}

function apply(): void {
  tried.value = true;
  const d = draft.value;
  const readable = [d.priceMin, d.priceMax].every((text) => parseMoney(text).ok) && [d.stockMin, d.stockMax].every((text) => readQuantity(text).ok);
  if (!readable) return;
  values.value = Object.fromEntries(
    Object.entries(d)
      .map(([key, text]) => [key, text.trim()])
      .filter(([, text]) => text !== ''),
  ) as ProductFilterValues;
  open.value = false;
}

function clear(): void {
  values.value = {};
  open.value = false;
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
</script>

<template>
  <ion-button
    fill="outline"
    color="medium"
    size="small"
    data-testid="inventory-products-filters"
    @click="show"
  >
    <HubIcon
      slot="start"
      name="ion:funnel"
    />
    {{ $t('inventory.products.filters.button') }}
    <ion-badge
      v-if="count"
      class="product-filters__count"
      color="primary"
      data-testid="inventory-products-filters-count"
    >
      {{ count }}
    </ion-badge>
  </ion-button>
  <FormModal
    v-model:open="open"
    :title="$t('inventory.products.filters.title')"
    testid="inventory-products-filters-panel"
    :submit-label="$t('inventory.products.filters.apply')"
    @submit="apply"
  >
    <div class="product-filters">
      <ion-input
        data-testid="inventory-products-filter-name"
        :model-value="draft.name"
        :label="$t('inventory.products.filters.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        @update:model-value="draft.name = text($event)"
      />
      <ion-input
        data-testid="inventory-products-filter-sku"
        :model-value="draft.sku"
        :label="$t('inventory.products.filters.sku')"
        label-placement="floating"
        fill="outline"
        mode="md"
        @update:model-value="draft.sku = text($event)"
      />
      <MoneyInput
        v-model="draft.priceMin"
        testid="inventory-products-filter-price-min"
        :label="$t('inventory.products.filters.priceMin')"
        :show-error="tried"
      />
      <MoneyInput
        v-model="draft.priceMax"
        testid="inventory-products-filter-price-max"
        :label="$t('inventory.products.filters.priceMax')"
        :show-error="tried"
      />
      <QuantityInput
        v-model="draft.stockMin"
        testid="inventory-products-filter-stock-min"
        :label="$t('inventory.products.filters.stockMin')"
        :show-error="tried"
      />
      <QuantityInput
        v-model="draft.stockMax"
        testid="inventory-products-filter-stock-max"
        :label="$t('inventory.products.filters.stockMax')"
        :show-error="tried"
      />
    </div>
    <template #footer="{ submit, cancel }">
      <ion-button
        fill="clear"
        color="medium"
        data-testid="inventory-products-filters-clear"
        @click="clear"
      >
        {{ $t('inventory.products.filters.clear') }}
      </ion-button>
      <ion-button
        fill="clear"
        @click="cancel"
      >
        {{ $t('inventory.common.cancel') }}
      </ion-button>
      <ion-button
        data-testid="inventory-products-filters-panel-submit"
        @click="submit"
      >
        {{ $t('inventory.products.filters.apply') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.product-filters {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.product-filters__count {
  margin-inline-start: 0.4rem;
}

@media (max-width: 575px) {
  .product-filters {
    grid-template-columns: 1fr;
  }
}
</style>
