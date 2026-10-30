<script setup lang="ts">
// A service tile of the till's grid (SALE-F38, SERVICE-F09): its photo (SERVICE-F34), or its initials over a colour
// derived from the name when it has none or the photo does not load, the name, the duration and the price; a service without a fixed price says how it is priced
// («From», «per hour», «Variable», «Free»: the till asks the amount). One without VAT is marked «VAT
// missing» (the business territory's tax: «IGIC missing», «IPSI missing»), looks blocked and still takes the tap (never the native `disabled`), as a product's tile.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import ItemImage from '../../../../../base/frontend/components/ItemImage.vue';
import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';

const props = defineProps<{ service: ServiceSaleOut }>();
const emit = defineEmits<{ pick: [service: ServiceSaleOut] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const taxName = useTaxName();

const blocked = computed(() => props.service.needs_tax_setup);
const label = computed(() => (blocked.value ? `${props.service.name} · ${t('sale.pos.notSellableNoTaxCategory', { tax: taxName.value })}` : undefined));
const price = computed(() => {
  const money = formatMoney(props.service.price, locale.value, business.value);
  const type = props.service.pricing_type;
  return type === 'fixed' ? money : t(`sale.pos.servicePrice.${type}`, { price: money });
});
</script>

<template>
  <button
    type="button"
    class="pos-tile"
    :class="{ 'pos-tile--blocked': blocked }"
    :data-testid="`pos-service-${service.id}`"
    :aria-disabled="blocked ? 'true' : undefined"
    :aria-label="label"
    :title="label"
    @click="emit('pick', service)"
  >
    <ItemImage
      class="pos-tile__thumb"
      :src="service.image_url"
      :name="service.name"
      aria-hidden="true"
    >
      <span
        v-if="blocked"
        class="pos-tile__warn"
      >
        <HubIcon name="ion:alert-circle" />
      </span>
    </ItemImage>
    <span class="pos-tile__info">
      <span class="pos-tile__name">{{ service.name }}</span>
      <span
        v-if="blocked"
        class="pos-tile__badge"
      >{{ $t('sale.pos.notSellableBadge', { tax: taxName }) }}</span>
      <span class="pos-tile__unit">{{ $t('sale.pos.serviceMinutes', { minutes: service.duration_minutes }) }}</span>
      <span class="pos-tile__price">{{ price }}</span>
    </span>
  </button>
</template>

<style scoped>
/* The very look of a product's tile (ProductTile.vue), so the grid reads as one. */
.pos-tile {
  display: flex;
  flex-direction: column;
  min-height: 8.4rem;
  margin: 0;
  padding: 0;
  overflow: hidden;
  font: inherit;
  text-align: left;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 14px;
  cursor: pointer;
  transition:
    border-color 0.12s,
    transform 0.05s;
}
.pos-tile:hover {
  border-color: var(--ion-color-primary, #0091ce);
}
.pos-tile:active {
  transform: scale(0.98);
}
.pos-tile--blocked {
  opacity: 0.72;
  border-style: dashed;
  cursor: not-allowed;
}
.pos-tile--blocked:hover {
  border-color: var(--ion-color-warning, #ffc409);
}
.pos-tile__thumb {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 4.85rem;
  font-size: 1.4rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.85);
}
.pos-tile__warn {
  position: absolute;
  top: 0.28rem;
  right: 0.28rem;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 1.5rem;
  height: 1.5rem;
  font-size: 1.05rem;
  color: var(--ion-color-warning-contrast, #000);
  background: var(--ion-color-warning, #ffc409);
  border-radius: 50%;
}
.pos-tile__info {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.2rem 0.4rem;
  padding: 0.5rem 0.6rem 0.65rem;
}
.pos-tile__name {
  grid-column: 1 / -1;
  overflow: hidden;
  font-size: 0.86rem;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pos-tile__badge {
  grid-column: 1 / -1;
  justify-self: start;
  max-width: 100%;
  overflow: hidden;
  padding: 0.08rem 0.38rem;
  font-size: 0.68rem;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: var(--ion-color-warning-contrast, #000);
  background: var(--ion-color-warning, #ffc409);
  border-radius: 999px;
}
.pos-tile__unit {
  grid-column: 1;
  font-size: 0.66rem;
  color: var(--ion-color-medium, #8b897f);
}
.pos-tile__price {
  grid-column: 2;
  font-size: 0.9rem;
  font-weight: 800;
  white-space: nowrap;
  color: var(--ion-color-primary, #0091ce);
}
@media (max-width: 820px) {
  .pos-tile {
    min-height: 8rem;
  }
  .pos-tile__price {
    font-size: 0.82rem;
  }
}
@media (max-width: 340px) {
  .pos-tile {
    min-height: 7.7rem;
  }
  .pos-tile__thumb {
    height: 4.5rem;
  }
}
</style>
