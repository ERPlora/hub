<script setup lang="ts">
// A service tile of the till's grid (SALE-F38, SERVICE-F09): its photo (SERVICE-F34), or its initials over a colour
// derived from the name when it has none or the photo does not load, the name, the duration and the price; a service without a fixed price says how it is priced
// («From», «per hour», «Variable», «Free»: the till asks the amount). One without VAT is marked «VAT
// missing» (the business territory's tax: «IGIC missing», «IPSI missing»), looks blocked and still takes the tap (never the native `disabled`), as a product's tile.
import { computed } from 'vue';

import type { ServiceSaleOut } from '../../../../service/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import PosItemTile from './PosItemTile.vue';

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
  <PosItemTile
    :testid="`pos-service-${service.id}`"
    :name="service.name"
    :price="price"
    :meta="$t('sale.pos.serviceMinutes', { minutes: service.duration_minutes })"
    :badge="blocked ? $t('sale.pos.notSellableBadge', { tax: taxName }) : undefined"
    :blocked="blocked"
    :label="label"
    :image-url="service.image_url"
    :image-reference="service.image"
    @pick="emit('pick', service)"
  />
</template>
