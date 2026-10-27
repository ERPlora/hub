<script setup lang="ts">
// The banner on top of Invoices and Series while the business's issuer is not set up (INVOICE-F21, «Antes de
// empezar»; the old pages' «You cannot invoice yet»): no ticket or invoice can be issued until then, and «Set up»
// opens Invoicing → Issuer; whoever may not change the issuer is told an administrator has to, as the Home's ⛔ tells
// them (gh:hub#435). It follows the live issuer (`invoice.issuer.get`, read by everyone who sees invoices,
// one subscription per tab with the Issuer page), so it goes away by itself once the issuer is saved anywhere.
// Nothing while it loads or when it cannot be read: the page says that itself.
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const session = useSession();
const canManage = computed(() => session.can('invoice.manage_issuer'));
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
      <template v-if="canManage">
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
      <!-- The note on its own line under the step, as base's strip says it (never a narrow column beside it). -->
      <span
        v-else
        class="issuer-notice__step"
      >
        <span
          class="issuer-notice__item"
          data-testid="invoice-issuer-notice-item"
        >{{ $t('invoice.issuerNotice.item') }}</span>
        <span
          class="issuer-notice__delegated"
          data-testid="invoice-issuer-notice-delegated"
        >{{ $t('invoice.issuerNotice.delegated') }}</span>
      </span>
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

.issuer-notice__step {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
}

.issuer-notice__step > .issuer-notice__item {
  align-self: flex-start;
}

.issuer-notice__delegated {
  font-style: italic;
}
</style>
