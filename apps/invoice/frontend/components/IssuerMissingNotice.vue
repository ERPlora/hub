<script setup lang="ts">
// The banner on top of Invoices and Series while the business's issuer is not set up (INVOICE-F21, «Antes de
// empezar»; the old pages' «You cannot invoice yet»): no ticket or invoice can be issued until then, and «Set up»
// opens Invoicing → Issuer. It follows the live issuer (`invoice.issuer.get`, read by everyone who sees invoices,
// one subscription per tab with the Issuer page), so it goes away by itself once the issuer is saved anywhere.
// Nothing while it loads or when it cannot be read: the page says that itself.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const { data: issuer } = useLive('invoice.issuer.get', () => ({}));
const missing = computed(() => issuer.value != null && !issuer.value.configured);
</script>

<template>
  <InlineFeedback
    v-if="missing"
    class="issuer-notice"
    tone="danger"
    :heading="$t('invoice.issuerNotice.heading')"
    data-testid="invoice-issuer-notice"
  >
    {{ $t('invoice.issuerNotice.message') }}
    <template #actions>
      <span
        class="issuer-notice__item"
        data-testid="invoice-issuer-notice-item"
      >{{ $t('invoice.issuerNotice.item') }}</span>
      <IonButton
        size="small"
        fill="outline"
        color="danger"
        data-testid="invoice-issuer-notice-setup"
        @click="router.push('/invoice/issuer')"
      >
        {{ $t('invoice.issuerNotice.setUp') }}
      </IonButton>
    </template>
  </InlineFeedback>
</template>

<style scoped>
.issuer-notice {
  margin-bottom: 0.75rem;
}

.issuer-notice__item {
  align-self: center;
  font-weight: 600;
}
</style>
