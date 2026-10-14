<script setup lang="ts">
// The charge sheet the till opens with «Charge» (WORKBOOK «Pantallas · Cobro», SALE-F01–F06, F22):
//   <CheckoutSheet v-model:open="charging" :order-id="orderId" :line-ids="markedLineIds"
//                  :order-version="order.version" :customer="customer" :staff-id="staffId" @charged="onCharged" />
// An `ion-modal`: from 821 px a centred 46rem card in two columns; below, a full-width sheet from the
// bottom (the old `.pay-sheet`). Its content (CheckoutPanel) is mounted only while it is shown, and anew
// on each opening: nothing is read while it is closed, and every opening is a new attempt with its own
// key. The ✕, the backdrop and Escape close it, never while charging. A charge closes it and hands the
// sale to the till (`charged`), also when it was the lookup of a lost answer that found it.
import { IonModal } from '@ionic/vue';
import { shallowRef, watch } from 'vue';

import type { CustomerSnapshot } from '../../../../customer/frontend/components/CustomerSearch.vue';
import type { SaleOut } from '../../operations';
import CheckoutPanel from './CheckoutPanel.vue';

withDefaults(
  defineProps<{
    orderId: string;
    /** The lines marked to pay on their own; empty = the whole check. */
    lineIds?: readonly string[];
    /** The check's version the till shows: a newer one refuses the charge (`sale.order_changed`). */
    orderVersion: number;
    customer?: CustomerSnapshot | null;
    staffId?: string | null;
  }>(),
  { lineIds: () => [], customer: null, staffId: null },
);

const open = defineModel<boolean>('open', { default: false });

const emit = defineEmits<{ charged: [sale: SaleOut] }>();

/** The content stays until the sheet has finished leaving, so it does not empty while it slides away. */
const shown = shallowRef(false);
/** One per opening: a fresh panel, so a fresh attempt. */
const opening = shallowRef(0);
const busy = shallowRef(false);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    opening.value += 1;
    shown.value = true;
  },
  { immediate: true },
);

/** Gone: closed from here, by the till, or by Ionic itself (backdrop, Escape, hardware back). */
function onDidDismiss(): void {
  shown.value = false;
  busy.value = false;
  open.value = false;
}

function onCharged(sale: SaleOut): void {
  emit('charged', sale);
  open.value = false;
}
</script>

<template>
  <ion-modal
    class="sale-checkout-modal"
    data-testid="sale-checkout-modal"
    :is-open="open"
    :backdrop-dismiss="!busy"
    :aria-label="$t('sale.checkout.title')"
    @did-dismiss="onDidDismiss"
  >
    <CheckoutPanel
      v-if="shown"
      :key="opening"
      :order-id="orderId"
      :line-ids="lineIds"
      :order-version="orderVersion"
      :customer="customer"
      :staff-id="staffId"
      @charged="onCharged"
      @close="open = false"
      @busy="busy = $event"
    />
  </ion-modal>
</template>

<style>
/* Not scoped: Ionic moves the modal under ion-app and wraps its content (`.ion-delegate-host`). Every rule
   hangs from `ion-modal.sale-checkout-modal`, so nothing leaks out. */
ion-modal.sale-checkout-modal {
  --width: min(calc(100% - 32px), 46rem);
  --height: auto;
  --max-height: calc(100% - 32px);
  --border-radius: var(--ep-radius-lg, 16px);
  --box-shadow: var(--ep-shadow-modal);
}

/* As tall as its content (Ionic's `.ion-page` would fill a fixed height); the panel scrolls inside. */
ion-modal.sale-checkout-modal .ion-delegate-host {
  position: relative;
  display: block;
  contain: content;
}

ion-modal.sale-checkout-modal .sale-checkout {
  max-height: calc(100vh - 32px);
  max-height: calc(100dvh - 32px);
}

:root.ion-palette-dark ion-modal.sale-checkout-modal {
  --backdrop-opacity: 0.6;
}

:root.ion-palette-dark ion-modal.sale-checkout-modal::part(content) {
  border: 1px solid var(--ion-border-color, #26282e);
}

/* Below 821 px two columns do not fit: a full-width sheet from the bottom, rounded on top only. */
@media (max-width: 820px) {
  ion-modal.sale-checkout-modal {
    --width: 100%;
    --max-height: calc(100% - var(--ion-safe-area-top, 0px) - 12px);
    --border-radius: var(--ep-radius-lg, 16px) var(--ep-radius-lg, 16px) 0 0;
    align-items: flex-end;
  }

  ion-modal.sale-checkout-modal .sale-checkout {
    max-height: calc(100vh - var(--ion-safe-area-top, 0px) - 12px);
    max-height: calc(100dvh - var(--ion-safe-area-top, 0px) - 12px);
  }
}
</style>
