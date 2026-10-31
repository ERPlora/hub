<script setup lang="ts">
// The product sheet (WORKBOOK «Ficha del producto»), the old detail modal: its photo on top, larger (or its initials,
// INVENTORY-F32), SKU, Price, Stock («—» for
// an article without stock control) and Status, and, with the permission to move stock and on a
// physical product, «Receive stock», «Count stock» and, when it tracks its stock, «Write off stock»
// (the page opens their dialog). For whoever can change products, «Mark sold out» or «Put back on sale»
// (INVENTORY-F29): the sheet shows the live row, so the button turns once the stream brings it; a
// refusal is said inside the sheet. The SKU's barcode on its white plate and, for whoever sees products,
// «Print barcode» (INVENTORY-F25): each press asks Printing's queue for one label and the sheet says which
// printer takes it, or that it waits for a «Label» printer; without the queue, the browser's print dialog.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { ApiError, type OutputOf, useCommand } from '@erplora/ui/sdk';
import { HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import ItemImage from '../../../../base/frontend/components/ItemImage.vue';
import { useT } from '../composables/useT';
import { formatMoney, formatQuantity, useBusinessMoney } from '../lib/format';
import { printInBrowser } from '../lib/print-label';
import BarcodePlate from './BarcodePlate.vue';
import type { StockAction } from './StockModal.vue';

type Product = OutputOf<'inventory.product.list'>['rows'][number];

const props = defineProps<{ product: Product | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ stock: [kind: StockAction] }>();

const { t, locale } = useT();
const business = useBusinessMoney();
const session = useSession();
const canMove = computed(() => session.can('inventory.adjust_stock') && props.product?.product_type === 'physical');
const canChange = computed(() => session.can('inventory.change_product'));

const status = computed(() => {
  const p = props.product;
  if (!p) return '';
  if (p.needs_tax_setup) return `${t('inventory.tax.unconfigured')} · ${t('inventory.tax.unconfiguredReason')}`;
  const active = p.is_active ? t('inventory.common.yes') : t('inventory.common.no');
  return p.is_sold_out ? `${active} · ${t('inventory.products.soldOut')}` : active;
});

const soldOut = useCommand('inventory.product.set_sold_out');
const printLabel = useCommand('inventory.product.print_label');
const error = ref('');
const labelSent = ref<{ printer: string | null } | null>(null);
const plate = ref<InstanceType<typeof BarcodePlate> | null>(null);
// Another product, or the sheet opened again: an old refusal or label is not this one's.
watch([() => props.product?.id, open], () => {
  error.value = '';
  labelSent.value = null;
});

async function print(): Promise<void> {
  const p = props.product;
  if (!p) return;
  error.value = '';
  labelSent.value = null;
  try {
    const queued = await printLabel.run({ id: p.id });
    labelSent.value = { printer: queued.printer_name };
  } catch (failure) {
    const svg = plate.value?.svg;
    if (failure instanceof ApiError && failure.code === 'inventory.label_queue_unavailable' && svg) {
      printInBrowser(svg, { sku: p.sku, name: p.name });
      return;
    }
    const reason = failure instanceof Error ? failure.message : '';
    error.value = t('inventory.products.label.error', { reason });
  }
}

async function setSoldOut(value: boolean): Promise<void> {
  if (!props.product) return;
  error.value = '';
  try {
    await soldOut.run({ id: props.product.id, sold_out: value });
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : t('inventory.products.soldOutError');
  }
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="product?.name ?? ''"
    testid="inventory-product-detail"
  >
    <ItemImage
      v-if="product"
      class="product-detail__photo"
      data-testid="inventory-product-detail-photo"
      :src="product.image_url"
      :name="product.name"
    />
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="inventory-product-detail-error"
    >
      {{ error }}
    </InlineFeedback>
    <InlineFeedback
      v-if="labelSent"
      :tone="labelSent.printer ? 'success' : 'warning'"
      data-testid="inventory-product-detail-label"
    >
      {{
        labelSent.printer
          ? $t('inventory.products.label.sent', { printer: labelSent.printer })
          : $t('inventory.products.label.queued')
      }}
    </InlineFeedback>
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
          {{ formatMoney(product.price, locale, business) }}
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
    <BarcodePlate
      v-if="product"
      ref="plate"
      :value="product.sku"
    />
    <template #footer="{ cancel }">
      <ion-button
        v-if="product"
        fill="outline"
        :disabled="printLabel.pending.value"
        data-testid="inventory-product-detail-print-label"
        @click="print"
      >
        <HubIcon
          slot="start"
          name="ion:pricetag-outline"
        />
        {{ printLabel.pending.value ? $t('inventory.products.label.printing') : $t('inventory.products.actions.printLabel') }}
      </ion-button>
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
      <template v-if="canChange && product">
        <ion-button
          v-if="product.is_sold_out"
          fill="outline"
          :disabled="soldOut.pending.value"
          data-testid="inventory-product-detail-back-on-sale"
          @click="setSoldOut(false)"
        >
          <HubIcon
            slot="start"
            name="ion:refresh-outline"
          />
          {{ $t('inventory.products.actions.backOnSale') }}
        </ion-button>
        <ion-button
          v-else
          fill="outline"
          :disabled="soldOut.pending.value"
          data-testid="inventory-product-detail-sold-out"
          @click="setSoldOut(true)"
        >
          <HubIcon
            slot="start"
            name="ion:ban-outline"
          />
          {{ $t('inventory.products.actions.soldOut') }}
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

<style scoped>
.product-detail__photo {
  width: 128px;
  height: 128px;
  margin: 0 auto 12px;
  font-size: 2.4rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 16px;
}
</style>
