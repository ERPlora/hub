<script setup lang="ts">
// The side group of the charge sheet (the old `.pay-side`, sales#324/#341): what the sale is. «Receipt» or
// «Invoice» and, with an invoice, its recipient right below; over the ticket limit no «Receipt» at all
// (the law), only the recipient, on top. Below 821 px the sheet opens on the tender, so an invoice folds
// into one summary line («Invoice · Bar Pepe SL») that opens with a tap; folding is CSS only, nothing
// typed is lost. Choosing «Invoice» opens it: it asks something right below.
import { HubIcon } from '@erplora/ui/shell';
import { computed } from 'vue';

import { useT } from '../../composables/useT';
import type { Recipient } from '../../lib/checkout/recipient';
import type { DocumentType } from '../../operations';
import DocumentChooser from './DocumentChooser.vue';
import RecipientForm from './RecipientForm.vue';

defineProps<{
  /** Above the ticket limit: an invoice by law. */
  overLimit: boolean;
  /** The ticket limit, in cents (the preview's `ticket_limit`). */
  ticketLimit: number | null;
}>();

const document = defineModel<DocumentType>('document', { required: true });
const recipient = defineModel<Recipient>('recipient', { required: true });
/** Unfolded on a phone. */
const open = defineModel<boolean>('open', { default: false });

const t = useT();

const foldable = computed(() => document.value === 'invoice');
const folded = computed(() => foldable.value && !open.value);
const summary = computed(() =>
  [t(document.value === 'invoice' ? 'sale.checkout.docInvoice' : 'sale.checkout.docTicket'), recipient.value.name.trim()]
    .filter(Boolean)
    .join(' · '),
);

function choose(next: DocumentType): void {
  document.value = next;
  if (next === 'invoice') open.value = true;
}
</script>

<template>
  <div
    class="pay-side"
    data-testid="sale-checkout-side"
    :data-folded="folded ? 'true' : undefined"
  >
    <button
      v-if="foldable"
      type="button"
      class="pay-side-summary"
      data-testid="sale-checkout-summary"
      :aria-expanded="open ? 'true' : 'false'"
      @click="open = !open"
    >
      <span class="pay-side-summary__text">{{ summary }}</span>
      <HubIcon
        :name="open ? 'ion:chevron-up-outline' : 'ion:chevron-down-outline'"
        aria-hidden="true"
      />
    </button>
    <RecipientForm
      v-if="overLimit"
      v-model="recipient"
      reason="limit"
      :max="ticketLimit"
    />
    <template v-else>
      <DocumentChooser
        :model-value="document"
        @update:model-value="choose"
      />
      <RecipientForm
        v-if="document === 'invoice'"
        v-model="recipient"
        reason="invoice"
        :max="ticketLimit"
      />
    </template>
  </div>
</template>

<style scoped>
.pay-side {
  display: flex;
  flex-direction: column;
  gap: 0.8rem;
}

/* The summary exists on a narrow sheet only (below). */
.pay-side-summary {
  display: none;
}

@media (max-width: 820px) {
  .pay-side-summary {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    min-height: 2.75rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid var(--ion-border-color, #e6e3db);
    border-radius: var(--ep-radius-sm, 10px);
    background: var(--ion-card-background, var(--ion-background-color, #fff));
    color: var(--ion-text-color, #1c1b18);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .pay-side-summary__text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .pay-side[data-folded] > :not(.pay-side-summary) {
    display: none;
  }
}
</style>
