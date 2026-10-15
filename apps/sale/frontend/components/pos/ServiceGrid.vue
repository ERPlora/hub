<script setup lang="ts">
// The till's grid of services (SALE-F38): the services Services offers (`service.service.list_for_sale`),
// followed live in windows of 100 (one subscription each; «Load more» opens the next), a tile each. «No
// services.» when there are none, a spinner until the first answer, the error with «Retry». Its total
// goes up (`total`) for the «Services» chip; a tap hands the service up (`pick`), where the page decides
// (blocked without VAT, its price asked when it has no fixed one).
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonSpinner } from '@ionic/vue';
import { watch } from 'vue';

import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useLiveWindows } from '../../composables/useLiveWindows';
import ServiceTile from './ServiceTile.vue';

const emit = defineEmits<{ pick: [service: ServiceSaleOut]; total: [total: number] }>();

const services = useLiveWindows<'service.service.list_for_sale', ServiceSaleOut>('service.service.list_for_sale', () => ({}), 100);

watch(
  () => services.total.value,
  (total) => total !== undefined && emit('total', total),
  { immediate: true },
);
</script>

<template>
  <div class="pos-grid">
    <InlineFeedback
      v-if="services.error.value && !services.rows.value.length"
      class="pos-grid__state"
      tone="danger"
      data-testid="pos-services-error"
    >
      {{ $t('sale.pos.servicesLoadFailed') }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="pos-services-retry"
          @click="services.refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <template v-else>
      <ServiceTile
        v-for="item in services.rows.value"
        :key="item.id"
        :service="item"
        @pick="emit('pick', $event)"
      />
      <div
        v-if="services.status.value === 'loading' && !services.rows.value.length"
        class="pos-grid__state"
        data-testid="pos-services-loading"
      >
        <ion-spinner />
      </div>
      <p
        v-else-if="!services.rows.value.length"
        class="pos-grid__state"
        role="status"
        data-testid="pos-services-empty"
      >
        {{ $t('sale.pos.noServices') }}
      </p>
      <button
        v-if="services.hasMore.value"
        type="button"
        class="pos-grid__more"
        data-testid="pos-services-more"
        @click="services.loadMore()"
      >
        {{ $t('sale.pos.loadMore') }}
      </button>
    </template>
  </div>
</template>

<style scoped>
/* The product grid's layout (ProductGrid.vue): the same columns, states and «Load more». */
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
</style>
