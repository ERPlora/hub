<script setup lang="ts">
// «Reprint» on a row of Sales (SALE-F29; the old hidden viewer): the sale's paper painted out of sight,
// always a «DUPLICATE», printed through the browser as soon as it is there; then the job ends (`done`).
// A document that cannot be loaded, or a browser that refuses to print, says «Could not print».
// The host mounts one per reprint and drops it on `done`: its subscriptions go with it.
import { toastError } from '@erplora/ui/shell';

import { useT } from '../../composables/useT';
import { printPaper } from '../../lib/print';
import SaleDocument from './SaleDocument.vue';

defineProps<{ saleId: string }>();

const emit = defineEmits<{ done: [] }>();

const t = useT();
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
</script>

<template>
  <div
    class="sale-reprint"
    hidden
  >
    <SaleDocument
      :sale-id="saleId"
      :duplicate="true"
      @ready="print"
      @failed="finish"
    />
  </div>
</template>
