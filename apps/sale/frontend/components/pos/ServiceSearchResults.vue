<script setup lang="ts">
// The services the till's search finds (SALE-F38): Services' offered services whose name holds what is
// typed (`service.service.list_for_sale`, live, 20 at a time), under «Services», after the products. A
// row shows the name, the duration (or why it cannot be sold) and the price; a tap hands the service
// up, where the same rules as a tile apply. Mounted only when the till sells services. As in the product
// search, a row's tap and its aria-disabled live on a native button inside the ion-item (an ion-item rewrites
// its own aria-disabled).
import { useLive } from '@erplora/ui/sdk';
import { IonItem, IonList, IonListHeader } from '@ionic/vue';
import { computed } from 'vue';

import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';

const props = defineProps<{ term: string }>();
const emit = defineEmits<{ pick: [service: ServiceSaleOut] }>();

const locale = useLocale();
const business = useBusinessMoney();
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
    >
      <button
        type="button"
        class="pos-search__row"
        :data-testid="`pos-search-service-${item.id}`"
        :aria-disabled="item.needs_tax_setup ? 'true' : undefined"
        @click="emit('pick', item)"
      >
        <span class="pos-search__text">
          <span class="pos-search__name">{{ item.name }}</span>
          <span
            class="pos-search__note"
            :class="{ 'pos-search__warn': item.needs_tax_setup }"
          >{{ item.needs_tax_setup ? $t('sale.pos.notSellableNoTaxCategory', { tax: taxName }) : $t('sale.pos.serviceMinutes', { minutes: item.duration_minutes }) }}</span>
        </span>
        <span class="pos-search__price">{{ formatMoney(item.price, locale, business) }}</span>
      </button>
    </ion-item>
  </ion-list>
</template>

<style scoped>
.pos-search__list {
  overflow-y: auto;
  background: transparent;
}
.pos-search__list ion-list-header {
  --background: transparent;
  border-radius: 10px;
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
</style>
