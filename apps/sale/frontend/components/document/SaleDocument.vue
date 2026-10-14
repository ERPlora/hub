<script setup lang="ts">
// The document of one sale (SALE-F29): `sale.sale.get` and the receipt settings (`sale.pos_settings.get`)
// followed live, «Loading document…» until both answered, «Error loading the document» (with the
// server's words and Retry) when either fails, then the paper. The host is told when the paper is
// painted (`ready`, with its element, what `printPaper` copies) or that it could not be (`failed`).
// Mount it only while it is wanted: its subscriptions live as long as it does.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, useTemplateRef, watch } from 'vue';

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

const error = computed(() => sale.error.value ?? settings.error.value);
/** The asked sale's document is here (another sale's, still on screen while the new one comes, is not). */
const loaded = computed(() => !error.value && sale.data.value?.id === props.saleId && !!settings.data.value);

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
    <ReceiptPaper
      v-else-if="loaded && sale.data.value"
      ref="paper"
      :sale="sale.data.value"
      :settings="settings.data.value"
      :duplicate="duplicate"
    />
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
