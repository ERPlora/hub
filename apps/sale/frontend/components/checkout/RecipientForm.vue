<script setup lang="ts">
// The recipient of an invoice (the old `.limit-capture`, hub#297, sales#317, #332): name, country, the
// kind of document (only abroad: the country decides, as Odoo's l10n_es_edi_verifactu), tax id and
// address. Amber while something is missing, saying what and why; green once complete. A new country
// resets the kind of document to the usual one there. The countries are the server's list (Customers'),
// named in the page language, Spain first. A Spanish tax ID that does not check, or a foreign one without
// its kind, is said under its box (as the server checks it, `apps.customer.tax_ids`); so is what the
// server refused on a field (`errors`).
import { HubIcon } from '@erplora/ui/shell';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed } from 'vue';

import { countryOptions } from '../../../../customer/frontend/components/CustomerSearch.vue';
import { useLocale, useT } from '../../composables/useT';
import { defaultIdType, HOME_COUNTRY, ID_TYPES, type Recipient, recipientComplete } from '../../lib/checkout/recipient';
import { recipientIssue } from '../../lib/checkout/taxId';
import { formatMoney, useBusinessMoney } from '../../lib/format';
import type { IdType } from '../../operations';

const props = defineProps<{
  /** Why it is asked: «Invoice» was chosen, or the total is over the ticket limit. */
  reason: 'invoice' | 'limit';
  /** The ticket limit, in cents (the preview's `ticket_limit`). */
  max?: number | null;
  /** What the server refused on a field of the recipient, in its words. */
  errors?: { taxId?: string; idType?: string };
}>();

const model = defineModel<Recipient>({ required: true });

const t = useT();
const locale = useLocale();
const business = useBusinessMoney();

const issue = computed(() => recipientIssue(model.value));
const complete = computed(() => recipientComplete(model.value) && !issue.value);
const taxIdError = computed(() => (issue.value === 'taxIdInvalid' ? t('sale.checkout.recipientErrors.taxIdInvalid') : props.errors?.taxId) || '');
const idTypeError = computed(() => (issue.value === 'idTypeRequired' ? t('sale.checkout.recipientErrors.idTypeRequired') : props.errors?.idType) || '');
const countries = computed(() => countryOptions(locale.value));
const heading = computed(() => {
  if (complete.value) return { title: t('sale.checkout.limitReadyTitle'), body: t('sale.checkout.limitReadyBody') };
  if (props.reason === 'limit') {
    return { title: t('sale.checkout.limitBlockedTitle'), body: t('sale.checkout.limitBlockedBody', { max: formatMoney(props.max, locale.value, business.value) }) };
  }
  return { title: t('sale.checkout.invoiceRecipientTitle'), body: t('sale.checkout.invoiceRecipientBody') };
});

type TextField = 'name' | 'taxId' | 'address';

function setText(field: TextField, value: unknown): void {
  model.value = { ...model.value, [field]: String(value ?? '') };
}

function setCountry(value: unknown): void {
  const country = String(value || HOME_COUNTRY);
  model.value = { ...model.value, country, idType: defaultIdType(country) };
}

function setIdType(value: unknown): void {
  model.value = { ...model.value, idType: String(value ?? '') as IdType };
}
</script>

<template>
  <div
    class="limit-capture"
    data-testid="sale-checkout-recipient"
    :data-reason="reason"
    :data-done="complete ? 'true' : undefined"
  >
    <div class="limit-head">
      <HubIcon
        :name="complete ? 'ion:receipt-outline' : 'ion:alert-circle-outline'"
        aria-hidden="true"
      />
      <div>
        <strong>{{ heading.title }}</strong>
        <p>{{ heading.body }}</p>
      </div>
    </div>
    <ion-input
      data-testid="sale-checkout-recipient-name"
      :label="$t('sale.checkout.fieldName')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      autocomplete="off"
      :value="model.name"
      @ion-input="setText('name', $event.detail.value)"
    />
    <ion-select
      data-testid="sale-checkout-recipient-country"
      :label="$t('sale.checkout.fieldCountry')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      interface="popover"
      :value="model.country"
      @ion-change="setCountry($event.detail.value)"
    >
      <ion-select-option
        v-for="country in countries"
        :key="country.value"
        :value="country.value"
      >
        {{ country.label }}
      </ion-select-option>
    </ion-select>
    <ion-select
      v-if="model.country !== HOME_COUNTRY"
      data-testid="sale-checkout-recipient-id-type"
      :label="$t('sale.checkout.fieldIdType')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      interface="popover"
      :value="model.idType"
      @ion-change="setIdType($event.detail.value)"
    >
      <ion-select-option
        v-for="code in ID_TYPES"
        :key="code"
        :value="code"
      >
        {{ t(`sale.checkout.idType.${code}`) }}
      </ion-select-option>
    </ion-select>
    <p
      v-if="model.country !== HOME_COUNTRY && idTypeError"
      class="recipient-error"
      role="alert"
      data-testid="sale-checkout-recipient-id-type-error"
    >
      {{ idTypeError }}
    </p>
    <ion-input
      data-testid="sale-checkout-recipient-tax-id"
      :label="$t('sale.checkout.fieldTaxId')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      autocomplete="off"
      :value="model.taxId"
      :class="{ 'ion-invalid': !!taxIdError, 'ion-touched': !!taxIdError }"
      @ion-input="setText('taxId', $event.detail.value)"
    />
    <p
      v-if="taxIdError"
      class="recipient-error"
      role="alert"
      data-testid="sale-checkout-recipient-tax-id-error"
    >
      {{ taxIdError }}
    </p>
    <ion-input
      data-testid="sale-checkout-recipient-address"
      :label="$t('sale.checkout.fieldAddress')"
      label-placement="stacked"
      fill="outline"
      mode="md"
      autocomplete="off"
      :value="model.address"
      @ion-input="setText('address', $event.detail.value)"
    />
  </div>
</template>

<style scoped>
.limit-capture {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  margin: 0 0 0.8rem;
  padding: 0.7rem 0.75rem;
  border: 1px solid var(--ion-color-warning, #e8a33d);
  border-radius: 0.7rem;
  background: color-mix(in srgb, var(--ion-color-warning, #e8a33d) 12%, transparent);
}

.limit-capture[data-done] {
  border-color: var(--ion-color-success, #2dd36f);
  background: color-mix(in srgb, var(--ion-color-success, #2dd36f) 10%, transparent);
}

.limit-head {
  display: flex;
  align-items: flex-start;
  gap: 0.55rem;
  margin-bottom: 0.25rem;
}

.limit-head ion-icon {
  flex: 0 0 auto;
  margin-top: 0.1rem;
  font-size: 1.35rem;
}

.limit-head strong {
  display: block;
  font-size: 0.98rem;
}

.limit-head p {
  margin: 0.15rem 0 0;
  color: var(--ep-text-muted, #646b78);
  font-size: 0.86rem;
}

.recipient-error {
  margin: 0.1rem 0.2rem 0;
  color: var(--ion-color-danger, #d9480f);
  font-size: 0.82rem;
}

/* Outlined boxes (sales#414): the label sits on the top border, so each box needs room above, and the
   selects get the same fill as the inputs over the tinted box. */
.limit-capture ion-input,
.limit-capture ion-select {
  --background: var(--ion-background-color, #fff);
  --padding-start: 0.6rem;
  --padding-end: 0.6rem;
  margin-top: 0.4rem;
  border-radius: 0.5rem;
}
</style>
