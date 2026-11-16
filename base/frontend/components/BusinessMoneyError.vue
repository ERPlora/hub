<script setup lang="ts">
// The notice of a window whose amounts wait for the business's money (hub#938): its «Save» waits in grey until
// `base.business.get` answers (an amount is read in the business's currency, never before), and when that read fails
// instead the window says so here — «The business's currency could not be read», the server's reason and «Retry» —
// rather than waiting in grey without a word. «Retry» asks the server again (the tab's stream reopens) and the notice
// goes while it asks; a new failure brings it back. Once the money is known a later failure says nothing: nothing waits
// for it. Every window that waits for the money places it, in one line, where it says its own refusals:
//   <BusinessMoneyError />
import { InlineFeedback } from '@erplora/ui/components';
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useBusinessMoneyRead } from '../lib/money';

const { money, error, retry } = useBusinessMoneyRead();

/** From the tap on «Retry» until the server answers again (the money or another error). */
const retrying = shallowRef(false);
watch([error, money], () => (retrying.value = false));

const failed = computed(() => !money.value && !!error.value && !retrying.value);

function askAgain(): void {
  retrying.value = true;
  retry();
}
</script>

<template>
  <InlineFeedback
    v-if="failed"
    role="alert"
    tone="danger"
    data-testid="base-money-error"
    :heading="$t('base.money.unreadable')"
  >
    {{ error?.message }}
    <template #actions>
      <ion-button
        size="small"
        fill="outline"
        data-testid="base-money-error-retry"
        @click="askAgain"
      >
        {{ $t('base.money.retry') }}
      </ion-button>
    </template>
  </InlineFeedback>
</template>
