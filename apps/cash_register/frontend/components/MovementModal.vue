<script setup lang="ts">
// «Cash movement · S-…» (CASH_REGISTER-F05; the old dashboard's movement panel): «Type» (Cash in: change
// from the safe; Cash out: a supplier paid, money to the bank), «Amount» always positive (the server gives
// the sign by the type), «Concept». From the screen the movement is always cash. The amount is the platform's money
// field (`MoneyInput`), read with its `parseMoney` as every amount of the Hub (hub#1160): one that is zero or
// cannot be read is said under it; the server's refusal (below zero, the session closed on another
// device) is read in the window, and a field it names says it until the person corrects that field. «Register» waits
// in grey until the business has answered its money (the amount is read in it; hub#921), and says so with «Retry» if
// that read fails (hub#938). Success says «Cash-in recorded (…)» or «Cash-out recorded (…)».
import { FormModal, type FormModalError, MoneyInput, parseMoney } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, shallowRef, watch } from 'vue';

import BusinessMoneyError from '../../../../base/frontend/components/BusinessMoneyError.vue';
import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';
import { useLocale, useT } from '../composables/useT';
import { formatMoney, useBusinessMoney } from '../lib/money';
import { refusal } from '../lib/refusal';
import type { ManualType } from '../operations';

const props = defineProps<{ session: { id: string; number: string } | null }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const command = useCommand('cash_register.movement.add');

const type = shallowRef<ManualType>('in');
const amount = shallowRef('');
const concept = shallowRef('');
/** «Register» was pressed: the amount says what is wrong with it even if it was never left. */
const tried = ref(false);
/** The amount read as no money at all (empty or 0): said under the field, never sent. */
const zero = ref(false);

watch(
  open,
  (now) => {
    if (!now) return;
    type.value = 'in';
    amount.value = '';
    concept.value = '';
    tried.value = false;
    zero.value = false;
    command.error.value = null;
  },
  { immediate: true },
);
watch(amount, () => {
  zero.value = false;
});

const error = computed<FormModalError | null>(() => refusal(command.error.value, t('cash_register.movement.failed')));
const amountError = (fieldErrors: Readonly<Record<string, string>>): string | undefined =>
  fieldErrors.amount ?? (zero.value ? t('cash_register.money.zero') : undefined);

async function confirm(): Promise<void> {
  const session = props.session;
  // No amount is read before the business answers its money: «1500» would be read with two decimals, whatever its
  // currency counts (in yen, 150000; hub#921).
  tried.value = true;
  const money = business.value;
  if (!session || !money) return;
  const read = parseMoney(amount.value, { money });
  if (!read.ok) return; // The field says why.
  zero.value = !read.cents;
  if (!read.cents) return;
  const cents = read.cents;
  try {
    await command.run({ session_id: session.id, type: type.value, amount: cents, description: concept.value.trim() });
  } catch {
    return; // The window shows `command.error`.
  }
  const key = type.value === 'in' ? 'cash_register.movement.doneIn' : 'cash_register.movement.doneOut';
  void toastSuccess(t(key, { amount: formatMoney(cents, locale.value, money) }));
  open.value = false;
}

const canDismiss = useUnsavedFormOnOpen('cash-register-movement', () => ({ type: type.value, amount: amount.value, concept: concept.value }), open);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    size="sm"
    testid="cash-register-movement"
    :title="$t('cash_register.movement.title', { number: session?.number ?? '' })"
    :submit-label="$t('cash_register.movement.submit')"
    :cancel-label="$t('cash_register.movement.cancel')"
    :pending="command.pending.value"
    :submit-disabled="!business"
    :error="error"
    @submit="confirm"
  >
    <template #default="{ fieldErrors }">
      <div class="cash-movement">
        <BusinessMoneyError />
        <ion-select
          data-testid="cash-register-movement-type"
          name="type"
          :label="$t('cash_register.movement.type')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          interface="popover"
          :value="type"
          :error-text="fieldErrors.type"
          :class="{ 'ion-invalid': !!fieldErrors.type, 'ion-touched': !!fieldErrors.type }"
          @ion-change="type = $event.detail.value === 'out' ? 'out' : 'in'"
        >
          <ion-select-option value="in">
            {{ $t('cash_register.types.in') }}
          </ion-select-option>
          <ion-select-option value="out">
            {{ $t('cash_register.types.out') }}
          </ion-select-option>
        </ion-select>
        <MoneyInput
          v-model="amount"
          testid="cash-register-movement-amount"
          name="amount"
          :label="$t('cash_register.movement.amount')"
          :money="business"
          :error-text="amountError(fieldErrors)"
          :show-error="tried"
        />
        <ion-input
          data-testid="cash-register-movement-concept"
          name="description"
          :label="$t('cash_register.movement.concept')"
          label-placement="stacked"
          fill="outline"
          mode="md"
          :maxlength="255"
          :value="concept"
          :error-text="fieldErrors.description"
          :class="{ 'ion-invalid': !!fieldErrors.description, 'ion-touched': !!fieldErrors.description }"
          @ion-input="concept = String($event.detail.value ?? '')"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.cash-movement {
  display: grid;
  gap: 0.85rem;
}
</style>
