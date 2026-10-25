<script setup lang="ts">
// «Cash movement · S-…» (CASH_REGISTER-F05; the old dashboard's movement panel): «Type» (Cash in: change
// from the safe; Cash out: a supplier paid, money to the bank), «Amount» always positive (the server gives
// the sign by the type), «Concept». From the screen the movement is always cash. An amount that is zero or
// cannot be read is said under its field; the server's refusal (below zero, the session closed on another
// device) is read in the window. Success says «Cash-in recorded (…)» or «Cash-out recorded (…)».
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { moneyDecimals, formatMoney, moneyRefusal, readMoney, useBusinessMoney } from '../lib/money';
import { refusal } from '../lib/refusal';
import type { ManualType } from '../operations';
import MoneyField from './MoneyField.vue';

const props = defineProps<{ session: { id: string; number: string } | null }>();

const open = defineModel<boolean>('open', { required: true });

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();
const command = useCommand('cash_register.movement.add');

const type = shallowRef<ManualType>('in');
const amount = shallowRef('');
const concept = shallowRef('');
const amountRefusal = shallowRef<string | null>(null);

watch(
  open,
  (now) => {
    if (!now) return;
    type.value = 'in';
    amount.value = '';
    concept.value = '';
    amountRefusal.value = null;
    command.error.value = null;
  },
  { immediate: true },
);

const error = computed<FormModalError | null>(() => refusal(command.error.value, t('cash_register.movement.failed')));
const amountError = computed(() => amountRefusal.value ?? error.value?.fields?.amount ?? null);

async function confirm(): Promise<void> {
  const session = props.session;
  if (!session) return;
  const read = readMoney(amount.value, moneyDecimals(business.value), business.value?.currency);
  amountRefusal.value = read.ok && !read.cents ? t('cash_register.money.zero') : moneyRefusal(read, t, locale.value, business.value);
  if (!read.ok || !read.cents) return;
  const cents = read.cents;
  try {
    await command.run({ session_id: session.id, type: type.value, amount: cents, description: concept.value.trim() });
  } catch {
    return; // The window shows `command.error`.
  }
  const key = type.value === 'in' ? 'cash_register.movement.doneIn' : 'cash_register.movement.doneOut';
  void toastSuccess(t(key, { amount: formatMoney(cents, locale.value, business.value) }));
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    size="sm"
    testid="cash-register-movement"
    :title="$t('cash_register.movement.title', { number: session?.number ?? '' })"
    :submit-label="$t('cash_register.movement.submit')"
    :cancel-label="$t('cash_register.movement.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="confirm"
  >
    <div class="cash-movement">
      <ion-select
        data-testid="cash-register-movement-type"
        :label="$t('cash_register.movement.type')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="type"
        @ion-change="type = $event.detail.value === 'out' ? 'out' : 'in'"
      >
        <ion-select-option value="in">
          {{ $t('cash_register.types.in') }}
        </ion-select-option>
        <ion-select-option value="out">
          {{ $t('cash_register.types.out') }}
        </ion-select-option>
      </ion-select>
      <MoneyField
        v-model="amount"
        testid="cash-register-movement-amount"
        :label="$t('cash_register.movement.amount')"
        :error="amountError"
      />
      <ion-input
        data-testid="cash-register-movement-concept"
        :label="$t('cash_register.movement.concept')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="255"
        :value="concept"
        @ion-input="concept = String($event.detail.value ?? '')"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.cash-movement {
  display: grid;
  gap: 0.85rem;
}
</style>
