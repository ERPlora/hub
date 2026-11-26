<script setup lang="ts">
// «Adjust» a tip (TIP-F06): its amount, in the business's money, and whom it belongs to (the active team of Staff), as
// they are, and «Reason». «Save» runs `tip.tip.update` with only what changed and the reason; the server asks for the
// reason, or for something to change, in its own words. In the open drawer the difference enters or leaves by itself.
import { Combo, type ComboOption, FormModal, MoneyInput, moneyFieldText } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonTextarea } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../../../sale/frontend/composables/useT';
import { refusal } from '../../../sale/frontend/lib/refusal';
import { useBusinessMoney } from '../../../../base/frontend/lib/money';
import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';
import { teamSearch } from '../lib/team';
import { adjustInput } from '../lib/tipInput';
import type { TipOut } from '../operations';

const props = defineProps<{ tip: TipOut | null }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const locale = useLocale();
const money = useBusinessMoney();
const search = teamSearch(useLiveClient());
const command = useCommand('tip.tip.update');

const amount = shallowRef('');
const member = shallowRef<ComboOption | null>(null);
const reason = shallowRef('');
/** The key of what the screen could not read in the amount. */
const amountError = shallowRef('');

watch(
  open,
  (now) => {
    const tip = props.tip;
    if (!now || !tip) return;
    amount.value = moneyFieldText(tip.amount, locale.value, money.value);
    member.value = tip.member_id ? { id: tip.member_id, label: tip.member_name } : null;
    reason.value = '';
    amountError.value = '';
    command.error.value = null;
  },
  { immediate: true },
);

const title = computed(() =>
  props.tip?.pool ? t('tip.adjust.poolTitle') : t('tip.adjust.title', { sale: props.tip?.sale_number ?? '' }),
);
const error = computed(() => refusal(command.error.value, t('tip.adjust.failed')));

async function save(): Promise<void> {
  const tip = props.tip;
  if (!tip) return;
  const built = adjustInput(tip, { amount: amount.value, memberId: member.value?.id ?? null, reason: reason.value }, money.value);
  if ('errors' in built) {
    amountError.value = built.errors.amount;
    return;
  }
  amountError.value = '';
  try {
    await command.run(built.input);
  } catch {
    return; // The window shows `command.error`.
  }
  toastSuccess(t('tip.adjust.done'));
  open.value = false;
}

const canDismiss = useUnsavedFormOnOpen('tip-adjust', () => reason.value, open);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    size="sm"
    testid="tip-adjust"
    :title="title"
    :submit-label="$t('tip.adjust.save')"
    :cancel-label="$t('tip.adjust.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <MoneyInput
        v-model="amount"
        testid="tip-adjust-amount"
        name="amount"
        :label="$t('tip.adjust.amount')"
        :money="money"
        :error-text="amountError ? $t(amountError) : fieldErrors.amount"
        :show-error="!!amountError || !!fieldErrors.amount"
      />
      <div class="ion-margin-top">
        <Combo
          testid="tip-adjust-member"
          name="member_id"
          :model-value="member"
          :search="search"
          :label="$t('tip.adjust.for')"
          :placeholder="$t('tip.adjust.searchPerson')"
          :empty-label="$t('tip.adjust.noPerson')"
          :error-text="fieldErrors.member_id"
          @update:model-value="member = $event"
        />
      </div>
      <ion-textarea
        class="ion-margin-top"
        :class="{ 'ion-invalid': !!fieldErrors.reason, 'ion-touched': !!fieldErrors.reason }"
        data-testid="tip-adjust-reason"
        name="reason"
        :label="$t('tip.adjust.reason')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="255"
        :auto-grow="true"
        :value="reason"
        :error-text="fieldErrors.reason"
        @ion-input="reason = String($event.detail.value ?? '')"
      />
    </template>
  </FormModal>
</template>
