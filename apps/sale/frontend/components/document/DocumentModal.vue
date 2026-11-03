<script setup lang="ts">
// The window of a sale's document (SALE-F29; the old `renderDocumentModal`), opened from Sales (a row,
// «Document») and by the till right after charging:
//   <DocumentModal v-model:open="showing" :sale-id="saleId" :duplicate="false" />
// No header: the paper on a light background (centred when short, scrolling when long), a floating ✕
// and a full-width print button in the footer. The document is a v-if child: nothing is subscribed
// while the window is closed. Every print from Sales is a «DUPLICATE» (the default); the till passes
// `false` for the first paper after charging. «Print» asks the printing queue first (`sale.sale.print`,
// PRINTING-F08): queued, a toast names the printer; not queued (Printing off, no receipt printer, a fiscal
// document pending) or the queue out of reach, the device prints the screen's paper (`printPaper`: inside the
// installed app, its print screen, hub#455), titled with the document's number; a failure says so, with the app's
// reason when it gives one.
import { useCommand } from '@erplora/ui/sdk';
import { HubIcon, toastError, toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonContent, IonFooter, IonModal, IonToolbar } from '@ionic/vue';
import { shallowRef, watch } from 'vue';

import { useT } from '../../composables/useT';
import { printRefusal, withReason } from '../../../../../base/frontend/lib/print-paper';
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

/** The painted paper, once there is one, and its number: what the print button prints, and the print's title. */
const paper = shallowRef<HTMLElement | null>(null);
const title = shallowRef('');

function painted(element: HTMLElement, number: string): void {
  paper.value = element;
  title.value = number;
}

// Closed, or another sale asked: the old paper is not this one's (the new one says `ready` again).
watch([open, () => props.saleId], ([now], [, before]) => {
  if (!now || props.saleId !== before) paper.value = null;
});

const queue = useCommand('sale.sale.print');
/** A print on its way: a second press waits for it. */
const sending = shallowRef(false);

async function print(): Promise<void> {
  const element = paper.value;
  const saleId = props.saleId;
  if (!element || !saleId || sending.value) return;
  sending.value = true;
  try {
    if (await queued(saleId)) return;
    // Not queued: the device prints the screen's paper (inside the app, its print screen, hub#455).
    await printPaper(element, { title: title.value });
  } catch (failure) {
    void toastError(withReason(t('sale.document.printFailed'), printRefusal(failure, t)));
  } finally {
    sending.value = false;
  }
}

/** Asks the printing queue; `true` when a printer took the document (a toast names it). */
async function queued(saleId: string): Promise<boolean> {
  try {
    const sent = await queue.run({ sale_id: saleId, duplicate: props.duplicate });
    if (!sent.queued) return false;
    void toastSuccess(t('sale.document.queued', { printer: sent.printer ?? '' }));
    return true;
  } catch {
    // The queue could not be asked: the screen's paper still prints.
    return false;
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
          @ready="painted"
          @failed="paper = null"
        />
      </div>
    </ion-content>
    <ion-footer class="sale-doc-modal__footer">
      <ion-toolbar>
        <ion-button
          expand="block"
          :disabled="!paper || sending"
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
