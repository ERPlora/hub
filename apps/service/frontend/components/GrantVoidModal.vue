<script setup lang="ts">
// SERVICE-F17 «Anular un bono vendido por error»: «Void this voucher?» says whose voucher and for how
// much (in the business's currency; a customer whose card is gone, by its reference), that it stays in the list as voided and that
// the money is refunded in Sales. The Reason is required; Void sends `service.grant.void` and closes.
// A refusal (used meanwhile, already voided) stays in the dialog.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { formatMoney, useBusinessMoney } from '../lib/format';
import type { GrantOut } from '../operations';

const props = defineProps<{ grant: GrantOut | null }>();
const open = defineModel<boolean>('open', { default: false });

const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const voiding = useCommand('service.grant.void');
const reason = ref('');

watch(open, (isOpen) => {
  if (!isOpen) return;
  reason.value = '';
  voiding.error.value = null;
});

const message = computed(() =>
  props.grant
    ? t('service.void.message', {
        customer: props.grant.customer_name ?? props.grant.customer_id,
        amount: formatMoney(props.grant.amount, locale.value, money.value),
      })
    : '',
);

async function confirm(): Promise<void> {
  if (!props.grant || !reason.value.trim()) return;
  try {
    await voiding.run({ id: props.grant.id, reason: reason.value.trim() });
  } catch {
    return; // The dialog paints the error.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="service-grant-void"
    role="alertdialog"
    size="sm"
    submit-color="danger"
    :title="t('service.void.title')"
    :submit-label="t('service.void.confirm')"
    :cancel-label="t('service.cancel')"
    :pending="voiding.pending.value"
    :error="voiding.error.value"
    :submit-disabled="!reason.trim()"
    @submit="confirm"
  >
    <template #default="{ fieldErrors }">
      <div class="service-grant-void">
        <p data-testid="service-grant-void-message">
          {{ message }}
        </p>
        <ion-textarea
          data-testid="service-grant-void-reason"
          :value="reason"
          :label="t('service.void.reason')"
          :helper-text="t('service.void.reasonHelp')"
          label-placement="floating"
          fill="outline"
          mode="md"
          auto-grow
          :maxlength="500"
          :error-text="fieldErrors.reason"
          @ion-input="reason = String($event.detail.value ?? '')"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.service-grant-void {
  display: grid;
  gap: 12px;
}
.service-grant-void p {
  margin: 0;
}
</style>
