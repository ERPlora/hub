<script setup lang="ts">
// PAYMENT-F02 «Registrar un pago»: «New payment» with the old panel's Method (the active ones, live),
// Date (today), Amount, Beneficiary and Concept, plus the Beneficiary IBAN and the Supplier invoice,
// and «Record payment» (`payment.payment.create`). The methods read has three states, told apart (the
// old payments#24): loading (the picker waits), could not be read (a notice with Retry), none yet (a
// notice with «Go to Methods»). The amount is read as a person writes it (`parseMoney`), in the business's currency
// and with its decimals (the field says which: «Amount (PLN)»); the server records the payment in that currency
// (the old payments#35). Until the business answers, «Record payment» waits: what was typed is read in its currency
// then, never guessed (hub#325). One that is not an amount, or is 0, is refused under the field before asking the
// server. The server's refusals stay
// in the form, under their field, with what was typed (the old pm#513). The attempt key is born with
// each opening and travels on every send of it: a retry after a lost answer records one payment, never
// two (the old payments#8); the next «New payment» is another attempt.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useT } from '../composables/useT';
import { localDay, useBusinessMoney } from '../lib/format';
import { parseMoney } from '../lib/money';
import type { PaymentOut } from '../operations';
import MoneyInput from './MoneyInput.vue';

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ created: [payment: PaymentOut] }>();

interface Form {
  methodId: string;
  date: string;
  amount: string;
  beneficiary: string;
  concept: string;
  iban: string;
  invoice: string;
}

const t = useT();
const router = useRouter();
const creation = useCommand('payment.payment.create');
const methods = useLive('payment.method.list', { is_active: true, limit: 100 });
const money = useBusinessMoney();

const blank = (): Form => ({ methodId: '', date: localDay(), amount: '', beneficiary: '', concept: '', iban: '', invoice: '' });
const form = ref<Form>(blank());
const newKey = (): string => globalThis.crypto.randomUUID();
/** This opening's attempt: the server records at most one payment per key. */
const attempt = ref(newKey());
/** A save was tried: the amount field says what is wrong with it even if it was never left. */
const tried = ref(false);
/** The amount is an amount but not above 0 (said under the field, never sent). */
const notPositive = ref(false);

watch(open, (isOpen) => {
  if (!isOpen) return;
  form.value = blank();
  attempt.value = newKey();
  tried.value = false;
  notPositive.value = false;
  creation.error.value = null;
});

const rows = computed(() => methods.data.value?.rows ?? []);
const loading = computed(() => methods.status.value === 'loading' && !methods.data.value);
const failed = computed(() => methods.status.value === 'error');
const none = computed(() => !!methods.data.value && rows.value.length === 0);
const complete = computed(
  () => !!money.value && !!form.value.methodId && !!form.value.date && !!form.value.amount.trim() && !!form.value.beneficiary.trim(),
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
function set<K extends keyof Form>(key: K, value: Form[K]): void {
  form.value = { ...form.value, [key]: value };
  if (key === 'amount') notPositive.value = false;
}

function amountError(fieldErrors: Readonly<Record<string, string>>): string | undefined {
  return fieldErrors.amount || (notPositive.value ? t('payment.money.notPositive') : undefined);
}

async function save(): Promise<void> {
  tried.value = true;
  if (!money.value) return; // The business has not answered: its currency's decimals are unknown.
  const read = parseMoney(form.value.amount, money.value);
  if (!read.ok) return; // The field says why.
  if (read.cents === null || read.cents <= 0) {
    notPositive.value = true;
    return;
  }
  const f = form.value;
  let created: PaymentOut;
  try {
    created = await creation.run({
      method_id: f.methodId,
      payment_date: f.date,
      amount: read.cents,
      beneficiary_name: f.beneficiary.trim(),
      concept: f.concept.trim(),
      beneficiary_iban: f.iban.trim(),
      supplier_invoice_ref: f.invoice.trim(),
      idempotency_key: attempt.value,
    });
  } catch {
    return; // The form paints the error; what was typed stays.
  }
  open.value = false;
  emit('created', created);
}

function goToMethods(): void {
  open.value = false;
  void router.push('/payment/methods');
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="payment-form"
    :title="$t('payment.payments.form.title')"
    :submit-label="$t('payment.payments.form.submit')"
    :pending="creation.pending.value"
    :error="creation.error.value"
    :submit-disabled="!complete"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="payment-form">
        <InlineFeedback
          v-if="failed"
          tone="danger"
          data-testid="payment-form-methods-error"
        >
          {{ $t('payment.payments.form.methodsError') }}
          <template #actions>
            <ion-button
              data-testid="payment-form-methods-retry"
              size="small"
              fill="outline"
              @click="methods.refresh()"
            >
              {{ $t('payment.live.retry') }}
            </ion-button>
          </template>
        </InlineFeedback>
        <InlineFeedback
          v-else-if="none"
          tone="warning"
          data-testid="payment-form-no-methods"
        >
          {{ $t('payment.payments.form.noMethods') }}
          <template #actions>
            <ion-button
              data-testid="payment-form-go-methods"
              size="small"
              fill="outline"
              @click="goToMethods"
            >
              {{ $t('payment.payments.form.goToMethods') }}
            </ion-button>
          </template>
        </InlineFeedback>
        <ion-select
          data-testid="payment-form-method"
          :value="form.methodId"
          :label="$t('payment.payments.form.method')"
          :placeholder="loading ? $t('payment.loading') : $t('payment.payments.form.methodPlaceholder')"
          :disabled="loading || failed || none"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.method_id"
          :class="invalid(fieldErrors.method_id)"
          @ion-change="set('methodId', text($event.detail.value))"
        >
          <ion-select-option
            v-for="method in rows"
            :key="method.id"
            :value="method.id"
          >
            {{ method.name }}
          </ion-select-option>
        </ion-select>
        <ion-input
          data-testid="payment-form-date"
          type="date"
          :value="form.date"
          :label="$t('payment.payments.form.date')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.payment_date"
          :class="invalid(fieldErrors.payment_date)"
          @ion-input="set('date', text($event.detail.value))"
          @ion-change="set('date', text($event.detail.value))"
        />
        <MoneyInput
          testid="payment-form-amount"
          :model-value="form.amount"
          :label="money ? t('payment.payments.form.amountIn', { currency: money.currency }) : t('payment.payments.form.amount')"
          :error-text="amountError(fieldErrors)"
          :show-error="tried"
          @update:model-value="set('amount', $event)"
        />
        <ion-input
          data-testid="payment-form-beneficiary"
          :value="form.beneficiary"
          :label="$t('payment.payments.form.beneficiary')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.beneficiary_name"
          :class="invalid(fieldErrors.beneficiary_name)"
          @ion-input="set('beneficiary', text($event.detail.value))"
        />
        <ion-input
          data-testid="payment-form-concept"
          :value="form.concept"
          :label="$t('payment.payments.form.concept')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="1000"
          :error-text="fieldErrors.concept"
          :class="invalid(fieldErrors.concept)"
          @ion-input="set('concept', text($event.detail.value))"
        />
        <ion-input
          data-testid="payment-form-iban"
          :value="form.iban"
          :label="$t('payment.payments.form.iban')"
          label-placement="floating"
          fill="outline"
          mode="md"
          autocapitalize="characters"
          :maxlength="64"
          :error-text="fieldErrors.beneficiary_iban"
          :class="invalid(fieldErrors.beneficiary_iban)"
          @ion-input="set('iban', text($event.detail.value))"
        />
        <ion-input
          data-testid="payment-form-invoice"
          :value="form.invoice"
          :label="$t('payment.payments.form.invoice')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="100"
          :error-text="fieldErrors.supplier_invoice_ref"
          :class="invalid(fieldErrors.supplier_invoice_ref)"
          @ion-input="set('invoice', text($event.detail.value))"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.payment-form {
  display: grid;
  gap: 14px;
}
</style>
