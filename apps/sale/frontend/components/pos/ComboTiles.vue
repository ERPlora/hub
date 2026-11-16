<script setup lang="ts">
// The menus on the till's grid (SALE-F12; Menus' COMBO-F07): the menus Menus has on sale and can complete
// (`combo.combo.for_sale`, live, up to 50), painted first in «All» as tiles of the grid, each with its photo (or its
// initials when it has none or it does not load, COMBO-F14), marked «Menu» with its name and closed price; a tap hands the menu up (`pick`) and the page opens its sheet. Nothing while it loads (the
// products are already there); a failed read says so with «Retry»; Menus off or not readable shows nothing.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import type { SaleComboOut } from '../../../../combo/frontend/operations';
import { useLocale, useT } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import PosItemTile from './PosItemTile.vue';

const emit = defineEmits<{ pick: [combo: SaleComboOut] }>();

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const { data, error, refresh } = useLive('combo.combo.for_sale', { limit: 50 });

const menus = computed(() => data.value?.rows ?? []);
/** Menus off or not readable is not a failure of the till: the menus are simply not offered. */
const failed = computed(() => !!error.value && !['app_inactive', 'permission_denied'].includes(error.value.code));
</script>

<template>
  <InlineFeedback
    v-if="failed"
    class="pos-menus__error"
    tone="danger"
    data-testid="pos-menus-error"
  >
    {{ $t('sale.pos.menu.loadFailed') }}
    <template #actions>
      <ion-button
        size="small"
        fill="outline"
        data-testid="pos-menus-retry"
        @click="refresh()"
      >
        {{ $t('sale.live.retry') }}
      </ion-button>
    </template>
  </InlineFeedback>
  <PosItemTile
    v-for="menu in menus"
    :key="menu.id"
    :testid="`pos-menu-${menu.id}`"
    :name="menu.name"
    :price="formatMoney(menu.price, locale, business)"
    :badge="t('sale.pos.menu.badge')"
    :image-url="menu.image_url"
    :image-reference="menu.image"
    @pick="emit('pick', menu)"
  />
</template>

<style scoped>
.pos-menus__error {
  grid-column: 1 / -1;
}
</style>
