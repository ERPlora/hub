<script setup lang="ts">
// One product of Inventory followed live (`inventory.product.get`) and handed up on every answer: the till's
// notice of a refused tap goes the moment the product can be sold again (SALE-F07, hub#442), wherever it was
// tapped (the grid in use or the search). Renderless. Mounted only while that notice is up (`useLive` has no
// «skip»). An error hands nothing up: the notice keeps what the till last knew.
import { useLive } from '@erplora/ui/sdk';
import { watch } from 'vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';

const props = defineProps<{ productId: string }>();
const emit = defineEmits<{ product: [product: ProductOut] }>();

const { data } = useLive('inventory.product.get', () => ({ id: props.productId }));

watch(
  data,
  (product) => {
    if (product) emit('product', product);
  },
  { immediate: true },
);
</script>

<template>
  <slot />
</template>
