<script setup lang="ts">
// The recipient of a full invoice (INVOICE-F03, F05; the fields Sales asks at the till, SALE-F04): the
// customer search of Customers (picking a card fills the fields with a COPY of its tax details; removing
// it keeps what is written), «Name or company name», «Country» (Customers' list, Spain first), «Document
// type» (only abroad; a new country resets it to the usual one there), «Tax ID» and «Address». What the
// server refused is said under its field (`fieldErrors`, by the command's field names) until what it judged
// is changed (hub#461); the next refusal says it again.
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, shallowRef, useTemplateRef, watch } from 'vue';

import CustomerSearch, { countryOptions, type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useLocale } from '../composables/useT';
import { defaultIdType, HOME_COUNTRY, ID_TYPES, type Recipient, recipientFrom } from '../lib/recipient';
import type { IdType } from '../operations';

const props = withDefaults(
  defineProps<{
    /** What the server refused, by field of the command (`customer_tax_id`…). */
    fieldErrors?: Readonly<Record<string, string>>;
  }>(),
  { fieldErrors: () => ({}) },
);

const model = defineModel<Recipient>({ required: true });

const locale = useLocale();
const countries = computed(() => countryOptions(locale.value));
const card = shallowRef<CustomerSnapshot | null>(null);
const choosing = shallowRef(false);
const root = useTemplateRef<HTMLElement>('root');

watch(card, (picked) => {
  model.value = picked ? recipientFrom(picked) : { ...model.value, customerId: null };
  // The fields changed with no keystroke: the form around them hears a native `input`, as from any field.
  root.value?.dispatchEvent(new Event('input', { bubbles: true }));
});

/** What the server judged to refuse each field: a tax ID is checked against its country and document type. */
const JUDGED_ON: Readonly<Record<string, readonly (keyof Recipient)[]>> = {
  customer_name: ['name'],
  customer_country: ['country'],
  customer_id_type: ['idType', 'country'],
  customer_tax_id: ['taxId', 'country', 'idType'],
  customer_address: ['address'],
};

/** The recipient when the last refusal came. */
const refusedOver = shallowRef<Recipient>(model.value);
watch(
  () => props.fieldErrors,
  () => {
    refusedOver.value = model.value;
  },
);

/** The server's message of a field, while what it judged is still as it was. */
function refusalOf(field: string): string | undefined {
  const untouched = (JUDGED_ON[field] ?? []).every((key) => model.value[key] === refusedOver.value[key]);
  return untouched ? props.fieldErrors[field] : undefined;
}

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

const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
</script>

<template>
  <div
    ref="root"
    class="invoice-recipient"
    data-testid="invoice-recipient"
  >
    <CustomerSearch
      v-model="card"
      v-model:open="choosing"
    />
    <ion-input
      data-testid="invoice-recipient-name"
      :label="$t('invoice.recipient.name')"
      label-placement="floating"
      fill="outline"
      mode="md"
      autocomplete="off"
      :maxlength="120"
      :value="model.name"
      :error-text="refusalOf('customer_name')"
      :class="invalid(refusalOf('customer_name'))"
      @ion-input="setText('name', $event.detail.value)"
    />
    <ion-select
      data-testid="invoice-recipient-country"
      :label="$t('invoice.recipient.country')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      :value="model.country"
      :error-text="refusalOf('customer_country')"
      :class="invalid(refusalOf('customer_country'))"
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
      data-testid="invoice-recipient-id-type"
      :label="$t('invoice.recipient.idType')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      :value="model.idType"
      :error-text="refusalOf('customer_id_type')"
      :class="invalid(refusalOf('customer_id_type'))"
      @ion-change="setIdType($event.detail.value)"
    >
      <ion-select-option
        v-for="code in ID_TYPES"
        :key="code"
        :value="code"
      >
        {{ $t(`invoice.recipient.idTypes.${code}`) }}
      </ion-select-option>
    </ion-select>
    <ion-input
      data-testid="invoice-recipient-tax-id"
      :label="$t('invoice.recipient.taxId')"
      label-placement="floating"
      fill="outline"
      mode="md"
      autocomplete="off"
      :maxlength="20"
      :value="model.taxId"
      :error-text="refusalOf('customer_tax_id')"
      :class="invalid(refusalOf('customer_tax_id'))"
      @ion-input="setText('taxId', $event.detail.value)"
    />
    <ion-input
      data-testid="invoice-recipient-address"
      :label="$t('invoice.recipient.address')"
      label-placement="floating"
      fill="outline"
      mode="md"
      autocomplete="off"
      :maxlength="500"
      :value="model.address"
      :error-text="refusalOf('customer_address')"
      :class="invalid(refusalOf('customer_address'))"
      @ion-input="setText('address', $event.detail.value)"
    />
  </div>
</template>

<style scoped>
.invoice-recipient {
  display: grid;
  gap: 14px;
}
</style>
