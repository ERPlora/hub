<script setup lang="ts">
// The document of one sale (SALE-F29): `sale.sale.get` and the receipt settings (`sale.pos_settings.get`)
// followed live, «Loading document…» until both answered, «Error loading the document» (with the
// server's words and Retry) when either fails, then the paper — above it, out of what prints, «Fiscal
// document pending» with «Issue now» while a document of the sale waits. The host is told when the
// paper is painted (`ready`, with its element, what `printPaper` copies) or that it could not be
// (`failed`). With VeriFactu on and readable, a sale with a fiscal document waits for that document's record
// too (VERIFACTU-F19): the paper carries its QR, a reprint included, and a record that cannot be read fails the
// document like the sale would — never a paper without its QR.
// Mount it only while it is wanted: its subscriptions live as long as it does.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, shallowRef, useTemplateRef, watch } from 'vue';

import FiscalRecordFollower, { type FiscalRecordState } from './FiscalRecordFollower.vue';
import PendingDocuments from './PendingDocuments.vue';
import ReceiptPaper from './ReceiptPaper.vue';

const props = defineProps<{
  saleId: string;
  /** A reprint: «DUPLICATE» on the paper. */
  duplicate: boolean;
}>();

const emit = defineEmits<{
  /** The paper is painted: its element. */
  ready: [paper: HTMLElement];
  /** It could not be loaded: the reason. */
  failed: [message: string];
}>();

const sale = useLive('sale.sale.get', () => ({ sale_id: props.saleId }));
const settings = useLive('sale.pos_settings.get', {});
const session = useSession();

/** VeriFactu on in this business and the right to read its records. */
const verifactuOn = computed(
  () => !!session.me.value?.apps.some((app) => app.label === 'verifactu' && app.state === 'on') && session.can('verifactu.view_record'),
);
/** The asked sale's fiscal document whose record the paper waits for; none without VeriFactu or a document. */
const recordOf = computed(() => (verifactuOn.value && sale.data.value?.id === props.saleId ? sale.data.value.invoice_id : null) ?? null);
const fiscal = shallowRef<FiscalRecordState>({ record: undefined, error: null });
watch(recordOf, () => {
  fiscal.value = { record: undefined, error: null };
});

const error = computed(() => sale.error.value ?? settings.error.value ?? (recordOf.value ? fiscal.value.error : null));
/** The asked sale's document is here (another sale's, still on screen while the new one comes, is not), with its
 *  fiscal record when it waits for one. */
const loaded = computed(
  () =>
    !error.value &&
    sale.data.value?.id === props.saleId &&
    !!settings.data.value &&
    (!recordOf.value || fiscal.value.record !== undefined),
);
const record = computed(() => (recordOf.value ? (fiscal.value.record ?? null) : null));

const paper = useTemplateRef<InstanceType<typeof ReceiptPaper>>('paper');

watch(
  loaded,
  (now) => {
    const element = paper.value?.$el as HTMLElement | undefined;
    if (now && element) emit('ready', element);
  },
  { flush: 'post' },
);
watch(error, (now) => {
  if (now) emit('failed', now.message);
});

function retry(): void {
  sale.refresh();
}
</script>

<template>
  <div class="sale-document">
    <FiscalRecordFollower
      v-if="recordOf"
      :key="recordOf"
      :invoice-id="recordOf"
      @change="fiscal = $event"
    />
    <InlineFeedback
      v-if="error"
      tone="danger"
      data-testid="sale-document-error"
      :heading="$t('sale.document.error')"
    >
      {{ error.message }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="sale-document-retry"
          @click="retry"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <template v-else-if="loaded && sale.data.value">
      <PendingDocuments
        v-if="sale.data.value.documents_pending"
        :sale-id="sale.data.value.id"
      />
      <ReceiptPaper
        ref="paper"
        :sale="sale.data.value"
        :settings="settings.data.value"
        :duplicate="duplicate"
        :record="record"
      />
    </template>
    <div
      v-else
      class="sale-document__loading"
      data-testid="sale-document-loading"
      role="status"
    >
      <ion-spinner
        name="crescent"
        aria-hidden="true"
      />
      <span>{{ $t('sale.document.loading') }}</span>
    </div>
  </div>
</template>

<style scoped>
.sale-document__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.6rem;
  padding: 2rem 1rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
</style>
