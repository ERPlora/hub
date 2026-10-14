<script setup lang="ts">
// The product sheet (WORKBOOK «Ficha del producto»), the old detail modal: SKU, Price, Stock («—» for
// an article without stock control) and Status, and, with the permission to move stock and on a
// physical product, «Receive stock», «Count stock» and, when it tracks its stock, «Write off stock»
// (the page opens their dialog). The barcode plate and «Print barcode» (INVENTORY-F25) wait for the Printing app.
import { FormModal } from '@erplora/ui/components';
import type { OutputOf } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';
import { computed } from 'vue';

import { useT } from '../composables/useT';
import { formatMoney, formatQuantity } from '../lib/format';
import type { StockAction } from './StockModal.vue';

type Product = OutputOf<'inventory.product.list'>['rows'][number];

const props = defineProps<{ product: Product | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ stock: [kind: StockAction] }>();

const { t, locale } = useT();
const session = useSession();
const canMove = computed(() => session.can('inventory.adjust_stock') && props.product?.product_type === 'physical');

const status = computed(() => {
  const p = props.product;
  if (!p) return '';
  if (p.needs_tax_setup) return `${t('inventory.tax.unconfigured')} · ${t('inventory.tax.unconfiguredReason')}`;
  return p.is_active ? t('inventory.common.yes') : t('inventory.common.no');
});
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="product?.name ?? ''"
    testid="inventory-product-detail"
  >
    <ion-list
      v-if="product"
      lines="full"
    >
      <ion-item data-testid="inventory-product-detail-sku">
        <ion-label>{{ $t('inventory.common.sku') }}</ion-label>
        <ion-note slot="end">
          {{ product.sku }}
        </ion-note>
      </ion-item>
      <ion-item data-testid="inventory-product-detail-price">
        <ion-label>{{ $t('inventory.common.price') }}</ion-label>
        <ion-note slot="end">
          {{ formatMoney(product.price, locale) }}
        </ion-note>
      </ion-item>
      <ion-item data-testid="inventory-product-detail-stock">
        <ion-label>{{ $t('inventory.common.stock') }}</ion-label>
        <ion-note slot="end">
          {{ product.tracks_stock ? formatQuantity(product.stock, locale) : '—' }}
        </ion-note>
      </ion-item>
      <ion-item data-testid="inventory-product-detail-status">
        <ion-label>{{ $t('inventory.common.status') }}</ion-label>
        <ion-note
          slot="end"
          :color="product.needs_tax_setup ? 'warning' : 'medium'"
        >
          {{ status }}
        </ion-note>
      </ion-item>
    </ion-list>
    <template #footer="{ cancel }">
      <template v-if="canMove">
        <ion-button
          fill="outline"
          data-testid="inventory-product-detail-receive"
          @click="emit('stock', 'receive')"
        >
          <HubIcon
            slot="start"
            name="ion:download-outline"
          />
          {{ $t('inventory.products.actions.receive') }}
        </ion-button>
        <ion-button
          fill="outline"
          data-testid="inventory-product-detail-count"
          @click="emit('stock', 'count')"
        >
          <HubIcon
            slot="start"
            name="ion:keypad-outline"
          />
          {{ $t('inventory.products.actions.count') }}
        </ion-button>
        <ion-button
          v-if="product?.tracks_stock"
          fill="outline"
          data-testid="inventory-product-detail-write-off"
          @click="emit('stock', 'write_off')"
        >
          <HubIcon
            slot="start"
            name="ion:warning-outline"
          />
          {{ $t('inventory.products.actions.writeOff') }}
        </ion-button>
      </template>
      <ion-button
        data-testid="inventory-product-detail-close-button"
        @click="cancel"
      >
        {{ $t('inventory.common.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>
