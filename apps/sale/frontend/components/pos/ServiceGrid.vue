<script setup lang="ts">
// The till's «Services» grid (SALE-F38): the services' tiles alone, in the product grid's columns, with their spinner
// and «No services.»; their total goes up (`total`) for the chips and a tap hands the service up (`pick`).
import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import ServiceTiles from './ServiceTiles.vue';

const emit = defineEmits<{ pick: [service: ServiceSaleOut]; total: [total: number] }>();
</script>

<template>
  <div class="pos-grid">
    <ServiceTiles
      alone
      @pick="emit('pick', $event)"
      @total="emit('total', $event)"
    />
  </div>
</template>

<style scoped>
/* The product grid's layout (ProductGrid.vue): the same columns. */
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
</style>
