<script setup lang="ts">
// «Reprint» on a row of Sales (SALE-F29; the old hidden viewer): it asks the printing queue for the sale's
// copy first (`sale.sale.print`, PRINTING-F08) — queued, a toast names the printer and the job ends —; not
// queued (Printing off, no receipt printer, a fiscal document pending) or the queue out of reach, the sale's
// paper is painted out of sight, always a «DUPLICATE», printed on the device as soon as it is there (the browser's
// dialog; inside the installed app, its print screen, hub#455); then the job ends (`done`). A document that cannot
// be loaded, or a print the browser or the app refuses, says «Could not print», with the app's reason when it gives
// one. The host mounts one per reprint and drops it on `done`: its subscriptions go with it.
import { useCommand } from '@erplora/ui/sdk';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { onMounted, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
import { printRefusal } from '../../../../../base/frontend/lib/print-paper';
import { printPaper } from '../../lib/print';
import SaleDocument from './SaleDocument.vue';

const props = defineProps<{ saleId: string }>();

const emit = defineEmits<{ done: [] }>();

const t = useT();
const queue = useCommand('sale.sale.print');
/** Not queued: the screen's paper is painted (and its subscriptions opened) to print it here. */
const here = shallowRef(false);
let finished = false;

function finish(failure?: string): void {
  if (finished) return;
  finished = true;
  if (failure !== undefined) {
    const failed = t('sale.document.printFailed');
    void toastError(failure ? `${failed}: ${failure}` : failed);
  }
  emit('done');
}

/** The paper is on its way to the device: painted again meanwhile, it is not printed twice. */
let printing = false;

async function print(paper: HTMLElement, title: string): Promise<void> {
  if (printing || finished) return;
  printing = true;
  try {
    // Inside the installed app, its print screen (hub#455): the job ends once the app has the paper.
    await printPaper(paper, { title });
  } catch (failure) {
    finish(printRefusal(failure, t) ?? '');
    return;
  }
  finish();
}

onMounted(async () => {
  try {
    const sent = await queue.run({ sale_id: props.saleId });
    if (sent.queued) {
      void toastSuccess(t('sale.document.queued', { printer: sent.printer ?? '' }));
      finish();
      return;
    }
  } catch {
    // The queue could not be asked: the screen's paper still prints.
  }
  here.value = true;
});
</script>

<template>
  <div
    class="sale-reprint"
    hidden
  >
    <SaleDocument
      v-if="here"
      :sale-id="saleId"
      :duplicate="true"
      @ready="print"
      @failed="finish"
    />
  </div>
</template>
