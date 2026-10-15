<script setup lang="ts">
// «Fiscal document pending» (SALE-F29; INVOICE-F06 in phase 1, which has no relay to issue it on its
// own): Invoicing could not issue a document of this sale in its write — its ticket or invoice, the
// rectifying invoice of its void or of a refund — (no issuer yet, no permission…). The notice says so
// and, to whoever may charge, offers «Issue now» (`sale.sale.issue_documents`); a refusal says why,
// worded by the server, and the notice stays. Once issued, the live sale drops the notice by itself.
//   <PendingDocuments v-if="sale.documents_pending" :sale-id="sale.id" />
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
import { refusal } from '../../lib/refusal';

const props = defineProps<{ saleId: string }>();

const t = useT();
const session = useSession();
const canIssue = computed(() => session.can('sale.take_payment'));
const issuing = useCommand('sale.sale.issue_documents');
const failure = shallowRef<string | null>(null);

async function issue(): Promise<void> {
  failure.value = null;
  try {
    await issuing.run({ sale_id: props.saleId });
    void toastSuccess(t('sale.document.pending.issued'));
  } catch (error) {
    const fallback = t('sale.document.pending.failed');
    failure.value = refusal(error, fallback)?.message ?? fallback;
  }
}
</script>

<template>
  <InlineFeedback
    class="sale-pending"
    tone="warning"
    data-testid="sale-documents-pending"
    :heading="$t('sale.document.pending.title')"
  >
    {{ $t('sale.document.pending.hint') }}
    <span
      v-if="failure"
      class="sale-pending__error"
      role="alert"
      data-testid="sale-documents-error"
    >{{ failure }}</span>
    <template
      v-if="canIssue"
      #actions
    >
      <ion-button
        size="small"
        fill="outline"
        data-testid="sale-documents-issue"
        :disabled="issuing.pending.value"
        @click="issue"
      >
        {{ $t('sale.document.pending.issue') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>

<style scoped>
.sale-pending {
  margin-bottom: 0.75rem;
}
.sale-pending__error {
  display: block;
  margin-top: 0.35rem;
  font-weight: 600;
  color: var(--ion-color-danger, #c5000f);
}
</style>
