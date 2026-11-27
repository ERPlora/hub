<script setup lang="ts">
// The services' tiles of the till's grid (SALE-F38): the services Services offers (`service.service.list_for_sale`),
// followed live in windows of 100 (one subscription each; «Load more» opens the next), a tile each, and the error with
// «Retry». `alone` (the «Services» grid) adds a spinner until the first answer and «No services.» when there are none;
// among other tiles («All») they say nothing while loading or when there are none. The total goes up (`total`) for the
// chips; a tap hands the service up (`pick`), where the page decides (blocked without VAT, its price asked when it has
// no fixed one).
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton, IonSpinner } from '@ionic/vue';
import { watch } from 'vue';

import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useLiveWindows } from '../../composables/useLiveWindows';
import ServiceTile from './ServiceTile.vue';

defineProps<{ alone?: boolean }>();
const emit = defineEmits<{ pick: [service: ServiceSaleOut]; total: [total: number] }>();

const services = useLiveWindows<'service.service.list_for_sale', ServiceSaleOut>('service.service.list_for_sale', () => ({}), 100);

watch(
  () => services.total.value,
  (total) => total !== undefined && emit('total', total),
  { immediate: true },
);
</script>

<template>
  <InlineFeedback
    v-if="services.error.value && !services.rows.value.length"
    class="pos-services__state"
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
    <template v-if="alone && !services.rows.value.length">
      <div
        v-if="services.status.value === 'loading'"
        class="pos-services__state"
        data-testid="pos-services-loading"
      >
        <ion-spinner />
      </div>
      <p
        v-else
        class="pos-services__state"
        role="status"
        data-testid="pos-services-empty"
      >
        {{ $t('sale.pos.noServices') }}
      </p>
    </template>
    <button
      v-if="services.hasMore.value"
      type="button"
      class="pos-services__more"
      data-testid="pos-services-more"
      @click="services.loadMore()"
    >
      {{ $t('sale.pos.loadMore') }}
    </button>
  </template>
</template>

<style scoped>
.pos-services__state {
  grid-column: 1 / -1;
  max-width: 34rem;
  margin: 0 auto;
  padding: 2.5rem 1rem;
  line-height: 1.45;
  text-align: center;
  color: var(--ion-color-medium, #8b897f);
}
.pos-services__more {
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
