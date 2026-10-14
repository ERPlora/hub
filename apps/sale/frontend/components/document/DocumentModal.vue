<script setup lang="ts">
// The window of a sale's document (SALE-F29; the old `renderDocumentModal`), opened from Sales (a row,
// «Document») and by the till right after charging:
//   <DocumentModal v-model:open="showing" :sale-id="saleId" :duplicate="false" />
// No header: the paper on a light background (centred when short, scrolling when long), a floating ✕
// and a full-width print button in the footer. The document is a v-if child: nothing is subscribed
// while the window is closed. Every print from Sales is a «DUPLICATE» (the default); the till passes
// `false` for the first paper after charging. Printing goes through the browser (`printPaper`) until
// the Printing app brings the network printer.
import { HubIcon, toastError } from '@erplora/ui/shell';
import { IonButton, IonContent, IonFooter, IonModal, IonToolbar } from '@ionic/vue';
import { shallowRef, watch } from 'vue';

import { useT } from '../../composables/useT';
import { printPaper } from '../../lib/print';
import SaleDocument from './SaleDocument.vue';

const props = withDefaults(
  defineProps<{
    saleId: string | null;
    /** «DUPLICATE» on the paper (every print from Sales). */
    duplicate?: boolean;
  }>(),
  { duplicate: true },
);

const open = defineModel<boolean>('open', { required: true });

const t = useT();

/** The painted paper, once there is one: what the print button prints. */
const paper = shallowRef<HTMLElement | null>(null);

// Closed, or another sale asked: the old paper is not this one's (the new one says `ready` again).
watch([open, () => props.saleId], ([now], [, before]) => {
  if (!now || props.saleId !== before) paper.value = null;
});

function print(): void {
  if (!paper.value) return;
  try {
    printPaper(paper.value);
  } catch {
    void toastError(t('sale.document.printFailed'));
  }
}
</script>

<template>
  <ion-modal
    class="sale-doc-modal"
    :is-open="open"
    :aria-label="$t('sale.document.title')"
    data-testid="sale-document-modal"
    @did-dismiss="open = false"
  >
    <ion-content class="sale-doc-modal__body">
      <ion-button
        slot="fixed"
        class="sale-doc-modal__close"
        fill="clear"
        color="medium"
        :aria-label="$t('sale.document.close')"
        data-testid="sale-document-close"
        @click="open = false"
      >
        <HubIcon
          slot="icon-only"
          name="ion:close"
        />
      </ion-button>
      <div class="sale-doc-modal__paper">
        <SaleDocument
          v-if="open && saleId"
          :sale-id="saleId"
          :duplicate="duplicate"
          @ready="paper = $event"
          @failed="paper = null"
        />
      </div>
    </ion-content>
    <ion-footer class="sale-doc-modal__footer">
      <ion-toolbar>
        <ion-button
          expand="block"
          :disabled="!paper"
          :aria-label="$t('sale.document.print')"
          data-testid="sale-document-print"
          @click="print"
        >
          <HubIcon
            slot="icon-only"
            name="ion:receipt-outline"
          />
        </ion-button>
      </ion-toolbar>
    </ion-footer>
  </ion-modal>
</template>

<style>
/* Not scoped: Ionic moves the modal to the app root. Every rule hangs from `ion-modal.sale-doc-modal`.
   The old document window: 440 × 720 at most, radius 14, the paper on the light background. */
ion-modal.sale-doc-modal {
  --width: min(440px, 100vw);
  --height: min(720px, 100vh);
  --border-radius: 14px;
}
ion-modal.sale-doc-modal .sale-doc-modal__body {
  --background: var(--ion-color-light, #f4f5f8);
}
ion-modal.sale-doc-modal .sale-doc-modal__close {
  top: 4px;
  right: 4px;
}
ion-modal.sale-doc-modal .sale-doc-modal__paper {
  box-sizing: border-box;
  min-height: 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 44px 12px 16px;
}
ion-modal.sale-doc-modal .sale-receipt {
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.12);
}
ion-modal.sale-doc-modal .sale-doc-modal__footer ion-toolbar {
  --padding-start: 12px;
  --padding-end: 12px;
}
</style>
