<script setup lang="ts">
// A product tile of the till's grid: its photo (INVENTORY-F32), or its initials over a colour derived from the name
// when it has none or the photo does not load, the name, the unit (when it is not «ud») and the price; never the SKU. A product without VAT (SALE-F07) is marked
// «VAT missing» («IGIC missing», «IPSI missing»: the business territory's tax), looks blocked and still takes the tap (never the native `disabled`: a touchscreen
// would swallow it and nobody would learn why); the grid answers that tap with the reason. A product sold out
// in Inventory («86», INVENTORY-F29) is greyed with «Sold out» and takes the tap the same way.
import { computed } from 'vue';

import type { ProductOut } from '../../../../inventory/frontend/operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import PosItemTile from './PosItemTile.vue';

const props = defineProps<{ product: ProductOut }>();
const emit = defineEmits<{ pick: [product: ProductOut] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const taxName = useTaxName();

const soldOut = computed(() => Boolean(props.product.is_sold_out));
const blocked = computed(() => !soldOut.value && props.product.needs_tax_setup);
const label = computed(() => {
  if (soldOut.value) return `${props.product.name} · ${t('sale.pos.soldOutBadge')}`;
  return blocked.value ? `${props.product.name} · ${t('sale.pos.notSellableNoTaxCategory', { tax: taxName.value })}` : undefined;
});
const badge = computed(() => {
  if (soldOut.value) return t('sale.pos.soldOutBadge');
  return blocked.value ? t('sale.pos.notSellableBadge', { tax: taxName.value }) : undefined;
});
const meta = computed(() => (props.product.unit === 'ud' ? undefined : props.product.unit));
</script>

<template>
  <PosItemTile
    :testid="`pos-product-${product.id}`"
    :name="product.name"
    :price="formatMoney(product.price, locale, business)"
    :meta="meta"
    :badge="badge"
    :blocked="blocked"
    :sold-out="soldOut"
    :label="label"
    :image-url="product.image_url"
    :image-reference="product.image"
    @pick="emit('pick', product)"
  />
</template>
