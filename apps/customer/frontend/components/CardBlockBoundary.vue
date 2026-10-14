<script setup lang="ts">
// The frame of another app's block on the card (CUSTOMER-F24): it renders the block with the only
// thing the card tells it, the customer's id; a block that breaks says so in its place and the card
// and the other blocks go on (WORKBOOK: «cada bloque enseña su propio error»).
import { type Component, onErrorCaptured, ref } from 'vue';

defineProps<{ block: Component; customerId: string }>();

const failed = ref(false);
onErrorCaptured((error) => {
  console.error('customer: a block of the card failed', error);
  failed.value = true;
  return false;
});
</script>

<template>
  <p
    v-if="failed"
    class="customer-card-block__error"
    data-testid="customer-card-block-error"
    role="alert"
  >
    {{ $t('customer.blocks.failed') }}
  </p>
  <component
    :is="block"
    v-else
    :customer-id="customerId"
  />
</template>

<style scoped>
.customer-card-block__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
  margin: 0;
}
</style>
