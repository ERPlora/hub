<script setup lang="ts">
// The menus on the till's grid (SALE-F12; Menus' COMBO-F07): the menus Menus has on sale and can complete
// (`combo.combo.for_sale`, live, up to 50), painted first in «All» as tiles of the grid, each with its photo (or its
// initials when it has none or it does not load, COMBO-F14), marked «Menu» with its name and closed price; a tap hands the menu up (`pick`) and the page opens its sheet. Nothing while it loads (the
// products are already there); a failed read says so with «Retry»; Menus off or not readable shows nothing.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';

import ItemImage from '../../../../../base/frontend/components/ItemImage.vue';
import type { SaleComboOut } from '../../../../combo/frontend/operations';
import { useLocale } from '../../composables/useT';
import { formatMoney, useBusinessMoney } from '../../lib/format';

const emit = defineEmits<{ pick: [combo: SaleComboOut] }>();

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
  <button
    v-for="menu in menus"
    :key="menu.id"
    type="button"
    class="pos-menu"
    :data-testid="`pos-menu-${menu.id}`"
    @click="emit('pick', menu)"
  >
    <ItemImage
      class="pos-menu__thumb"
      fit="contain"
      :src="menu.image_url"
      :name="menu.name"
      aria-hidden="true"
    />
    <span class="pos-menu__info">
      <span class="pos-menu__name">{{ menu.name }}</span>
      <span
        class="pos-menu__badge"
        :data-testid="`pos-menu-${menu.id}-badge`"
      >{{ $t('sale.pos.menu.badge') }}</span>
      <span class="pos-menu__price">{{ formatMoney(menu.price, locale, business) }}</span>
    </span>
  </button>
</template>

<style scoped>
.pos-menus__error {
  grid-column: 1 / -1;
}
.pos-menu {
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
}
.pos-menu:hover {
  border-color: var(--ion-color-primary, #0091ce);
}
.pos-menu:active {
  transform: scale(0.98);
}
.pos-menu__thumb {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 4.85rem;
  font-size: 1.4rem;
  font-weight: 800;
  color: rgba(255, 255, 255, 0.85);
}
.pos-menu__info {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: end;
  gap: 0.2rem 0.4rem;
  padding: 0.5rem 0.6rem 0.65rem;
}
.pos-menu__name {
  grid-column: 1 / -1;
  overflow: hidden;
  font-size: 0.86rem;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.pos-menu__badge {
  grid-column: 1;
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
  color: var(--ion-color-primary-contrast, #fff);
  background: var(--ion-color-primary, #0091ce);
  border-radius: 999px;
}
.pos-menu__price {
  grid-column: 2;
  font-size: 0.9rem;
  font-weight: 800;
  white-space: nowrap;
  color: var(--ion-color-primary, #0091ce);
}
@media (max-width: 820px) {
  .pos-menu {
    min-height: 8rem;
  }
  .pos-menu__price {
    font-size: 0.82rem;
  }
}
@media (max-width: 340px) {
  .pos-menu {
    min-height: 7.7rem;
  }
  .pos-menu__thumb {
    height: 4.5rem;
  }
}
</style>
