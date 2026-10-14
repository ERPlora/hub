<script setup lang="ts">
// «Receipt» or «Invoice» (the old `.pay-docformat`, hub#962): the same two-up buttons as the payment
// methods, the other question the counter asks out loud («do you need an invoice?»). It only chooses:
// what the sheet starts on, and hiding it above the ticket limit, are the sheet's.
import type { DocumentType } from '../../operations';

const model = defineModel<DocumentType>({ required: true });

const DOCUMENTS: { value: DocumentType; key: string }[] = [
  { value: 'ticket', key: 'sale.checkout.docTicket' },
  { value: 'invoice', key: 'sale.checkout.docInvoice' },
];
</script>

<template>
  <div
    class="pay-docformat"
    role="group"
    data-testid="sale-checkout-doc"
    :aria-label="$t('sale.checkout.documentFormat')"
  >
    <button
      v-for="doc in DOCUMENTS"
      :key="doc.value"
      type="button"
      class="pm-btn"
      :data-testid="`sale-checkout-doc-${doc.value}`"
      :aria-pressed="model === doc.value ? 'true' : 'false'"
      @click="model = doc.value"
    >
      {{ $t(doc.key) }}
    </button>
  </div>
</template>

<style scoped>
.pay-docformat {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.5rem;
}

.pm-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: var(--ep-touch-lg, 56px);
  padding: 0 0.6rem;
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 12px;
  background: var(--ion-card-background, var(--ion-background-color, #fff));
  color: var(--ion-text-color, #1c1b18);
  font: inherit;
  font-size: 0.95rem;
  font-weight: 700;
  cursor: pointer;
}

.pm-btn[aria-pressed='true'] {
  border-color: var(--ion-color-primary, #0091ce);
  color: var(--ion-color-primary, #0091ce);
  box-shadow: var(--ep-ring-accent, inset 0 0 0 1px var(--ion-color-primary, #0091ce));
}

.pm-btn:focus-visible {
  outline: 2px solid var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}
</style>
