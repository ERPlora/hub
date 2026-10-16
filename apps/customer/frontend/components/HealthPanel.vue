<script setup lang="ts">
// «Health and allergies» of a card (CUSTOMER-F32): allergies and the last sensitivity (patch) test,
// special category data (GDPR art. 9), kept only with the person's explicit permission. Without it,
// «Ask for permission» shows the exact words to read out and «They said yes» stores THOSE words as
// the proof (`customer.health.grant`). With it, the data shows — the allergies as a warning, for whoever
// does the service — and «Edit» saves them (`customer.health.update`). «Withdraw permission» asks
// first, because it erases the data (`customer.health.withdraw`). The block is live
// (`customer.health.detail`) and never part of the card other apps read.
import { ConfirmDialog, formatDateTime, InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastSuccess } from '@erplora/ui/shell';
import { IonButton, IonInput, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, ref } from 'vue';

import { refusalFields, refusalOutsideFields } from '../lib/apiErrors';
import { formatDay } from '../lib/dates';
import { useCustomerI18n } from '../lib/useCustomerI18n';
import type { HealthTestResult } from '../operations';

const props = defineProps<{
  customerId: string;
  /** Who manages cards may ask, edit and withdraw; the others read. */
  editable: boolean;
}>();

/** Bump it when `customer.health.notice` changes: who said yes to WHICH words. */
const NOTICE_VERSION = 'health-v1';
/** Fields the form can show a refusal under. */
const FIELDS = ['allergies', 'sensitivity_test_on', 'sensitivity_test_result'] as const;

const { t, locale } = useCustomerI18n();

const { data, error, status } = useLive('customer.health.detail', () => ({ customer_id: props.customerId }));

const grant = useCommand('customer.health.grant');
const withdraw = useCommand('customer.health.withdraw');
const update = useCommand('customer.health.update');
const busy = computed(() => grant.pending.value || withdraw.pending.value || update.pending.value);

const granted = computed(() => data.value?.consent === 'granted');
const failure = computed(() =>
  [grant.error.value, update.error.value].map((err) => refusalOutsideFields(err, FIELDS)).find(Boolean) ?? '',
);
const fieldErrors = computed(() => refusalFields(update.error.value));
const invalid = (key: string) => ({ 'ion-invalid': !!fieldErrors.value[key], 'ion-touched': !!fieldErrors.value[key] });

/** The permission is being asked and not answered yet. */
const asking = ref(false);
/** The form is open. */
const editing = ref(false);
/** The «withdraw» dialog is open. */
const withdrawing = ref(false);

const allergies = ref('');
const testOn = ref('');
const result = ref<HealthTestResult>('');

function clearErrors(): void {
  grant.error.value = null;
  update.error.value = null;
}

function ask(): void {
  clearErrors();
  asking.value = true;
}

async function record(): Promise<void> {
  try {
    await grant.run({
      customer_id: props.customerId,
      // The words travel as shown, not as a key: the proof is what the person heard.
      notice_text: t('customer.health.notice'),
      notice_version: NOTICE_VERSION,
      source: 'counter',
    });
  } catch {
    return;
  }
  asking.value = false;
  void toastSuccess(t('customer.health.recorded'));
}

function edit(): void {
  clearErrors();
  allergies.value = data.value?.allergies ?? '';
  testOn.value = data.value?.sensitivity_test_on ?? '';
  result.value = data.value?.sensitivity_test_result ?? '';
  editing.value = true;
}

async function save(): Promise<void> {
  try {
    await update.run({
      customer_id: props.customerId,
      allergies: allergies.value,
      sensitivity_test_on: testOn.value || null,
      sensitivity_test_result: result.value,
    });
  } catch {
    return; // the refusal shows under its field or in the panel; what was typed stays.
  }
  editing.value = false;
  void toastSuccess(t('customer.health.saved'));
}

function askWithdraw(): void {
  withdraw.error.value = null;
  withdrawing.value = true;
}

async function takeBack(): Promise<void> {
  try {
    await withdraw.run({ customer_id: props.customerId, source: 'counter' });
  } catch {
    return; // the dialog shows the refusal.
  }
  withdrawing.value = false;
  editing.value = false;
  void toastSuccess(t('customer.health.withdrawn'));
}

const consentLine = computed(() => {
  const block = data.value;
  if (!block?.consent_at) return '';
  return [t('customer.health.given', { when: formatDateTime(block.consent_at, locale.value) }), block.consent_by]
    .filter(Boolean)
    .join(' · ');
});
const testLine = computed(() => {
  const block = data.value;
  if (!block?.sensitivity_test_on) return t('customer.health.noTest');
  const parts = [t('customer.health.test', { date: formatDay(block.sensitivity_test_on, locale.value) })];
  if (block.sensitivity_test_result) parts.push(t(`customer.health.results.${block.sensitivity_test_result}`));
  return parts.join(' · ');
});
</script>

<template>
  <div
    class="customer-health"
    data-testid="customer-health"
  >
    <h3>{{ $t('customer.health.heading') }}</h3>
    <p
      v-if="status === 'error' && !data"
      class="customer-health__error"
      data-testid="customer-health-error"
      role="alert"
    >
      {{ $t('customer.health.loadError') }}: {{ error?.message }}
    </p>
    <p
      v-else-if="!data"
      class="customer-health__muted"
      data-testid="customer-health-loading"
    >
      {{ $t('customer.common.loading') }}
    </p>
    <template v-else>
      <InlineFeedback
        v-if="failure"
        tone="danger"
        data-testid="customer-health-failure"
      >
        {{ failure }}
      </InlineFeedback>

      <template v-if="!granted">
        <p
          class="customer-health__muted"
          data-testid="customer-health-intro"
        >
          {{ $t('customer.health.intro') }}
        </p>
        <p
          v-if="data.consent === 'withdrawn' && data.consent_at"
          class="customer-health__muted"
          data-testid="customer-health-withdrawn"
        >
          {{ $t('customer.health.withdrawnOn', { when: formatDateTime(data.consent_at, locale) }) }}
        </p>
        <template v-if="editable">
          <ion-button
            v-if="!asking"
            size="small"
            data-testid="customer-health-ask"
            :disabled="busy"
            @click="ask"
          >
            {{ $t('customer.health.ask') }}
          </ion-button>
          <div
            v-else
            class="customer-health__ask"
            data-testid="customer-health-asking"
          >
            <p class="customer-health__notice">
              {{ $t('customer.health.notice') }}
            </p>
            <p class="customer-health__muted">
              {{ $t('customer.consent.askHint') }}
            </p>
            <ion-button
              size="small"
              data-testid="customer-health-confirm"
              :disabled="busy"
              @click="record"
            >
              {{ $t('customer.consent.confirm') }}
            </ion-button>
            <ion-button
              size="small"
              fill="outline"
              data-testid="customer-health-ask-cancel"
              @click="asking = false"
            >
              {{ $t('customer.common.cancel') }}
            </ion-button>
          </div>
        </template>
      </template>

      <template v-else>
        <p
          class="customer-health__muted customer-health__small"
          data-testid="customer-health-consent"
        >
          {{ consentLine }}
        </p>
        <form
          v-if="editing"
          class="customer-health__form"
          data-testid="customer-health-form"
          novalidate
          @submit.prevent="save"
        >
          <ion-textarea
            v-model="allergies"
            data-testid="customer-health-allergies-input"
            :label="$t('customer.health.allergiesLabel')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :auto-grow="true"
            :maxlength="2000"
            :error-text="fieldErrors.allergies"
            :class="invalid('allergies')"
          />
          <ion-input
            v-model="testOn"
            type="date"
            data-testid="customer-health-date-input"
            :label="$t('customer.health.dateLabel')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.sensitivity_test_on"
            :class="invalid('sensitivity_test_on')"
          />
          <ion-select
            v-model="result"
            data-testid="customer-health-result-input"
            :label="$t('customer.health.resultLabel')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            :class="invalid('sensitivity_test_result')"
          >
            <ion-select-option value="">
              {{ $t('customer.health.noResult') }}
            </ion-select-option>
            <ion-select-option value="negative">
              {{ $t('customer.health.results.negative') }}
            </ion-select-option>
            <ion-select-option value="positive">
              {{ $t('customer.health.results.positive') }}
            </ion-select-option>
          </ion-select>
          <div class="customer-health__actions">
            <ion-button
              type="submit"
              size="small"
              data-testid="customer-health-save"
              :disabled="busy"
            >
              {{ $t('customer.common.save') }}
            </ion-button>
            <ion-button
              size="small"
              fill="outline"
              data-testid="customer-health-edit-cancel"
              @click="editing = false"
            >
              {{ $t('customer.common.cancel') }}
            </ion-button>
          </div>
        </form>
        <div
          v-else
          data-testid="customer-health-data"
        >
          <p
            class="customer-health__line"
            :class="{ 'customer-health__alert': !!data.allergies }"
            data-testid="customer-health-allergies"
          >
            {{ data.allergies ? $t('customer.health.allergies', { text: data.allergies }) : $t('customer.health.noAllergies') }}
          </p>
          <p
            class="customer-health__line"
            data-testid="customer-health-test"
          >
            {{ testLine }}
          </p>
          <div
            v-if="editable"
            class="customer-health__actions"
          >
            <ion-button
              size="small"
              data-testid="customer-health-edit"
              :disabled="busy"
              @click="edit"
            >
              {{ $t('customer.common.edit') }}
            </ion-button>
            <ion-button
              size="small"
              fill="outline"
              color="danger"
              data-testid="customer-health-withdraw"
              :disabled="busy"
              @click="askWithdraw"
            >
              {{ $t('customer.health.withdraw') }}
            </ion-button>
          </div>
        </div>
      </template>
    </template>

    <ConfirmDialog
      v-model:open="withdrawing"
      testid="customer-health-withdraw-dialog"
      tone="danger"
      :title="$t('customer.health.withdrawTitle')"
      :message="$t('customer.health.withdrawMessage')"
      :confirm-label="$t('customer.health.withdrawConfirm')"
      confirm-icon="ion:trash-outline"
      :pending="withdraw.pending.value"
      :error="withdraw.error.value"
      @confirm="takeBack"
    />
  </div>
</template>

<style scoped>
.customer-health h3 {
  margin: 0.25rem 0 0.5rem;
  font-size: 1rem;
}

.customer-health__muted {
  opacity: 0.7;
}

.customer-health__small {
  font-size: 0.8rem;
}

.customer-health__line {
  margin: 0.375rem 0;
  overflow-wrap: anywhere;
}

/* The allergies, as a warning for whoever does the service (Fresha's and Phorest's client alerts). */
.customer-health__alert {
  padding: 0.5rem 0.75rem;
  border-left: 4px solid var(--ion-color-warning, #ffc409);
  border-radius: var(--ep-radius, 8px);
  background: rgba(var(--ion-color-warning-rgb, 255, 196, 9), 0.14);
  font-weight: 600;
}

.customer-health__ask,
.customer-health__form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.customer-health__notice {
  font-weight: 600;
  margin: 0.25rem 0;
}

.customer-health__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.customer-health__error {
  color: var(--ion-color-danger);
  font-size: 0.875rem;
}
</style>
