<script setup lang="ts">
// The VeriFactu notice above the till's grid (SALE-F07; VeriFactu's `issue_blocker`): when VeriFactu refuses new
// sales now (a business filing in production with no way to the AEAT), the till says so before anyone charges,
// in VeriFactu's own words, and «Review VeriFactu» takes whoever can configure it to its settings. Nothing while
// it can sell, nor when VeriFactu cannot be read: the charge itself would say why. The page mounts it only with
// VeriFactu on and readable (`useLive` has no «skip»).
import { InlineFeedback } from '@erplora/ui/components';
import { useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed } from 'vue';
import { useRouter } from 'vue-router';

const router = useRouter();
const session = useSession();
const canConfigure = computed(() => session.can('verifactu.configure'));

const { data, error } = useLive('verifactu.config.get', {});

const blocker = computed(() => (error.value ? null : (data.value?.issue_blocker ?? null)));
</script>

<template>
  <InlineFeedback
    v-if="blocker"
    class="pos-fiscal"
    tone="danger"
    data-testid="pos-fiscal-notice"
  >
    <strong>{{ $t('sale.pos.fiscal.title') }}</strong>
    {{ blocker.message }}
    <template
      v-if="canConfigure"
      #actions
    >
      <ion-button
        size="small"
        fill="outline"
        data-testid="pos-fiscal-review"
        @click="router.push('/verifactu/config')"
      >
        {{ $t('sale.pos.fiscal.review') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>

<style scoped>
.pos-fiscal {
  margin-bottom: 0.68rem;
}
</style>
