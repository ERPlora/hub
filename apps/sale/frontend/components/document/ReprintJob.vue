<script setup lang="ts">
// «Reprint» on a row of Sales (SALE-F29; the old hidden viewer): it asks the printing queue for the sale's
// copy first (`sale.sale.print`, PRINTING-F08) — queued, a toast names the printer and the job ends —; not
// queued (Printing off, no receipt printer, a fiscal document pending) or the queue out of reach, the sale's
// paper is painted out of sight, always a «DUPLICATE», printed through the browser as soon as it is there;
// then the job ends (`done`). A document that cannot be loaded, or a browser that refuses to print, says
// «Could not print». The host mounts one per reprint and drops it on `done`: its subscriptions go with it.
import { useCommand } from '@erplora/ui/sdk';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { onMounted, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
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

function print(paper: HTMLElement): void {
  try {
    printPaper(paper);
  } catch {
    finish('');
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
