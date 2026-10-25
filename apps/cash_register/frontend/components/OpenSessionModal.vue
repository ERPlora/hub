<script setup lang="ts">
// «Open cash session» (CASH_REGISTER-F03; the old dashboard's open panel): «Drawer» when the business has
// drawers (the only one is chosen alone; with several it is optional), «Opening float» as it is read
// (empty is 0), «Notes». An amount that cannot be read is said under its field and nothing is sent. The
// server numbers the session and keeps the rules (one open at a time, a float required): its refusal is
// read inside the window, at its field. Success says «Session opened» and closes; the table and the
// «Open session» button follow by themselves (live).
import { FormModal, type FormModalError } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { currencyDecimals, formatMoney, moneyFieldText, moneyRefusal, readMoney, useCurrency } from '../lib/money';
import { refusal } from '../lib/refusal';
import MoneyField from './MoneyField.vue';

const props = withDefaults(defineProps<{ unassignedCash?: number }>(), { unassignedCash: 0 });

const open = defineModel<boolean>('open', { required: true });
const emit = defineEmits<{ opened: [] }>();

const t = useT();
const locale = useLocale();
const currency = useCurrency();
const registers = useLive('cash_register.register.list', { is_active: true, limit: 100 });
const command = useCommand('cash_register.session.open');

const registerId = shallowRef('');
const balance = shallowRef('');
const notes = shallowRef('');
/** The field's own refusal (what was typed is no amount), before anything is sent. */
const balanceRefusal = shallowRef<string | null>(null);

const drawers = computed(() => registers.data.value?.rows ?? []);

watch(
  open,
  (now) => {
    if (!now) return;
    registerId.value = drawers.value.length === 1 ? drawers.value[0].id : '';
    balance.value = '';
    notes.value = '';
    balanceRefusal.value = null;
    command.error.value = null;
  },
  { immediate: true },
);
// The drawers may answer after the window opened: the only one is chosen alone.
watch(drawers, (now) => {
  if (now.length === 1 && !registerId.value) registerId.value = now[0].id;
});

const error = computed<FormModalError | null>(() => refusal(command.error.value, t('cash_register.open.failed')));
const balanceError = computed(() => balanceRefusal.value ?? error.value?.fields?.opening_balance ?? null);
const unassigned = computed(() => (props.unassignedCash > 0 ? formatMoney(props.unassignedCash, locale.value, currency.value) : ''));

async function confirm(): Promise<void> {
  const read = readMoney(balance.value, currencyDecimals(currency.value), currency.value);
  balanceRefusal.value = moneyRefusal(read, t, locale.value, currency.value);
  if (!read.ok) return;
  try {
    await command.run({
      ...(registerId.value ? { register_id: registerId.value } : {}),
      ...(read.cents !== null ? { opening_balance: read.cents } : {}),
      opening_notes: notes.value.trim(),
    });
  } catch {
    return; // The window shows `command.error`.
  }
  void toastSuccess(t('cash_register.open.done'));
  open.value = false;
  emit('opened');
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="cash-register-open"
    :title="$t('cash_register.open.title')"
    :submit-label="$t('cash_register.open.submit')"
    :cancel-label="$t('cash_register.open.cancel')"
    :pending="command.pending.value"
    :error="error"
    @submit="confirm"
  >
    <div class="cash-open">
      <p
        v-if="unassigned"
        class="cash-open__hint"
        data-testid="cash-register-open-unassigned"
      >
        {{ $t('cash_register.open.unassigned', { cash: unassigned }) }}
      </p>
      <ion-select
        v-if="drawers.length"
        data-testid="cash-register-open-register"
        :label="$t('cash_register.open.register')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        interface="popover"
        :value="registerId"
        @ion-change="registerId = String($event.detail.value ?? '')"
      >
        <ion-select-option value="">
          {{ $t('cash_register.open.noRegister') }}
        </ion-select-option>
        <ion-select-option
          v-for="drawer in drawers"
          :key="drawer.id"
          :value="drawer.id"
        >
          {{ drawer.name }}
        </ion-select-option>
      </ion-select>
      <MoneyField
        v-model="balance"
        testid="cash-register-open-balance"
        :label="$t('cash_register.open.balance')"
        :placeholder="moneyFieldText(0, locale, currencyDecimals(currency))"
        :error="balanceError"
      />
      <ion-input
        data-testid="cash-register-open-notes"
        :label="$t('cash_register.open.notes')"
        label-placement="stacked"
        fill="outline"
        mode="md"
        :maxlength="1000"
        :placeholder="$t('cash_register.open.optional')"
        :value="notes"
        @ion-input="notes = String($event.detail.value ?? '')"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.cash-open {
  display: grid;
  gap: 0.85rem;
}
.cash-open__hint {
  margin: 0;
  font-size: 0.9rem;
  color: var(--ion-color-warning-shade, #8a6d00);
}
</style>
