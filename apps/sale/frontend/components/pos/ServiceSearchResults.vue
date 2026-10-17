<script setup lang="ts">
// The services the till's search finds (SALE-F38): Services' offered services whose name holds what is
// typed (`service.service.list_for_sale`, live, 20 at a time), under «Services», after the products. A
// row shows the name, the duration (or why it cannot be sold) and the price; a tap hands the service
// up, where the same rules as a tile apply. Mounted only when the till sells services.
import { useLive } from '@erplora/ui/sdk';
import { IonItem, IonLabel, IonList, IonListHeader, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale } from '../../composables/useT';
import { formatMoney } from '../../lib/format';

const props = defineProps<{ term: string }>();
const emit = defineEmits<{ pick: [service: ServiceSaleOut] }>();

const locale = useLocale();
const taxName = useTaxName();
const { data } = useLive('service.service.list_for_sale', () => ({ search: props.term, limit: 20, offset: 0 }));
const rows = computed(() => data.value?.rows ?? []);
</script>

<template>
  <ion-list
    v-if="rows.length"
    class="pos-search__list"
  >
    <ion-list-header data-testid="pos-search-services-title">
      {{ $t('sale.pos.services') }}
    </ion-list-header>
    <ion-item
      v-for="item in rows"
      :key="item.id"
      button
      :detail="false"
      :data-testid="`pos-search-service-${item.id}`"
      :aria-disabled="item.needs_tax_setup ? 'true' : undefined"
      @click="emit('pick', item)"
    >
      <ion-label>
        <h3>{{ item.name }}</h3>
        <p :class="{ 'pos-search__warn': item.needs_tax_setup }">
          {{ item.needs_tax_setup ? $t('sale.pos.notSellableNoTaxCategory', { tax: taxName }) : $t('sale.pos.serviceMinutes', { minutes: item.duration_minutes }) }}
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
</template>

<style scoped>
.pos-search__list {
  overflow-y: auto;
  background: transparent;
}
.pos-search__list ion-item,
.pos-search__list ion-list-header {
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
</style>
