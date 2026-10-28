<script setup lang="ts">
// PRICING-F02, F03: the old table's side panel as a dialog. «New price list» asks for Code and Name
// (required), Currency (the business's, its country's, as `base.business.get` says it: empty until it
// answers, then filled unless the person typed one; emptied, none is sent and the server takes the
// business's), Tax (Business default by default), Customer group (searched in Customers; empty = no group),
// From and Until, and «General list» (for everybody and in the business's currency: off and disabled while a
// group or another currency is chosen, or the business has not answered). A row's Edit opens «Editing price list — {name}» without
// the general switch (its own action) and «Save» sends only what changed (no group =
// `customer_group_id: null`, an emptied day = `null`).
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/format';
import { searchGroups } from '../lib/pickers';
import { groupName } from '../lib/rules';
import type { PriceListIn, PriceListOut, PriceListPatchIn } from '../operations';

type Basis = 'business' | 'included' | 'excluded';
const BASES: readonly Basis[] = ['business', 'included', 'excluded'];

const props = withDefaults(defineProps<{ priceList?: PriceListOut | null }>(), { priceList: null });
const open = defineModel<boolean>('open', { default: false });

interface Form {
  code: string;
  name: string;
  currency: string;
  basis: Basis;
  group: ComboOption | null;
  validFrom: string;
  validUntil: string;
  isDefault: boolean;
}

const t = useT();
const money = useBusinessMoney();
/** The business's currency (its country's); unknown until it answers. */
const businessCurrency = computed(() => money.value?.currency);
const search = searchGroups(useLiveClient());
const creation = useCommand('pricing.price_list.create');
const update = useCommand('pricing.price_list.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.priceList ? update.error.value : creation.error.value));
const title = computed(() =>
  props.priceList ? t('pricing.lists.form.titleEdit', { name: props.priceList.name }) : t('pricing.lists.form.titleNew'),
);

const basisOf = (value: boolean | null): Basis => (value === null ? 'business' : value ? 'included' : 'excluded');
const taxOf = (basis: Basis): boolean | null => (basis === 'business' ? null : basis === 'included');

function blank(): Form {
  return { code: '', name: '', currency: businessCurrency.value ?? '', basis: 'business', group: null, validFrom: '', validUntil: '', isDefault: false };
}

function fromList(list: PriceListOut): Form {
  return {
    code: list.code,
    name: list.name,
    currency: list.currency,
    basis: basisOf(list.tax_included),
    group: list.customer_group_id ? { id: list.customer_group_id, label: groupName(list.customer_group_id, list.customer_group_name, t) } : null,
    validFrom: list.valid_from ?? '',
    validUntil: list.valid_until ?? '',
    isDefault: list.is_default,
  };
}

const form = ref<Form>(blank());

watch(
  () => [open.value, props.priceList?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = props.priceList ? fromList(props.priceList) : blank();
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

// A new list takes the business's currency when it answers after the dialog opened, unless one was typed.
watch(businessCurrency, (currency) => {
  if (currency && open.value && !props.priceList && !form.value.currency.trim()) form.value = { ...form.value, currency };
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const day = (value: string): string | null => value.trim() || null;

/** A general list is for everybody and in the business's currency. */
const canBeGeneral = computed(
  () => !form.value.group && !!businessCurrency.value && form.value.currency.trim().toUpperCase() === businessCurrency.value,
);

function pickGroup(option: ComboOption | null): void {
  // A general list is for everybody: choosing a group takes the mark off.
  form.value = { ...form.value, group: option, isDefault: option ? false : form.value.isDefault };
}

function setCurrency(value: string): void {
  const general = !!businessCurrency.value && value.trim().toUpperCase() === businessCurrency.value;
  form.value = { ...form.value, currency: value, isDefault: general ? form.value.isDefault : false };
}

function patch(list: PriceListOut): PriceListPatchIn {
  const f = form.value;
  const out: PriceListPatchIn = { id: list.id };
  if (f.code.trim() !== list.code) out.code = f.code.trim();
  if (f.name.trim() !== list.name) out.name = f.name.trim();
  if (f.currency.trim().toUpperCase() !== list.currency) out.currency = f.currency.trim().toUpperCase();
  if (taxOf(f.basis) !== list.tax_included) out.tax_included = taxOf(f.basis);
  if ((f.group?.id ?? null) !== list.customer_group_id) out.customer_group_id = f.group?.id ?? null;
  if (day(f.validFrom) !== list.valid_from) out.valid_from = day(f.validFrom);
  if (day(f.validUntil) !== list.valid_until) out.valid_until = day(f.validUntil);
  return out;
}

function created(): PriceListIn {
  const f = form.value;
  const currency = f.currency.trim().toUpperCase();
  return {
    code: f.code.trim(),
    name: f.name.trim(),
    // Empty: none sent, the server takes the business's.
    ...(currency ? { currency } : {}),
    tax_included: taxOf(f.basis),
    customer_group_id: f.group?.id ?? null,
    valid_from: day(f.validFrom),
    valid_until: day(f.validUntil),
    is_default: f.isDefault,
  };
}

async function save(): Promise<void> {
  try {
    if (props.priceList) await update.run(patch(props.priceList));
    else await creation.run(created());
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="pricing-list-form"
    :title="title"
    :submit-label="priceList ? $t('pricing.lists.form.save') : $t('pricing.lists.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.code.trim() || !form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="pricing-form">
        <ion-input
          data-testid="pricing-list-form-code"
          :value="form.code"
          :label="$t('pricing.lists.form.code')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="50"
          :error-text="fieldErrors.code"
          :class="invalid(fieldErrors.code)"
          @ion-input="form = { ...form, code: text($event.detail.value) }"
        />
        <ion-input
          data-testid="pricing-list-form-name"
          :value="form.name"
          :label="$t('pricing.lists.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="200"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <div class="pricing-form__row">
          <ion-input
            data-testid="pricing-list-form-currency"
            :value="form.currency"
            :label="$t('pricing.lists.form.currency')"
            label-placement="floating"
            fill="outline"
            mode="md"
            autocapitalize="characters"
            :maxlength="3"
            :error-text="fieldErrors.currency"
            :class="invalid(fieldErrors.currency)"
            @ion-input="setCurrency(text($event.detail.value))"
          />
          <ion-select
            data-testid="pricing-list-form-tax"
            :value="form.basis"
            :label="$t('pricing.lists.form.tax')"
            label-placement="floating"
            fill="outline"
            mode="md"
            interface="popover"
            :error-text="fieldErrors.tax_included"
            @ion-change="form = { ...form, basis: $event.detail.value as Basis }"
          >
            <ion-select-option
              v-for="basis in BASES"
              :key="basis"
              :value="basis"
            >
              {{ t(`pricing.taxBasis.${basis}`) }}
            </ion-select-option>
          </ion-select>
        </div>
        <Combo
          testid="pricing-list-form-group"
          :model-value="form.group"
          :search="search"
          :label="t('pricing.lists.form.group')"
          :placeholder="t('pricing.lists.form.noGroup')"
          clearable
          :error-text="fieldErrors.customer_group_id || fieldErrors.customer_group"
          @update:model-value="pickGroup"
        />
        <div class="pricing-form__row">
          <ion-input
            data-testid="pricing-list-form-valid_from"
            type="date"
            :value="form.validFrom"
            :label="$t('pricing.lists.form.validFrom')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.valid_from"
            :class="invalid(fieldErrors.valid_from)"
            @ion-input="form = { ...form, validFrom: text($event.detail.value) }"
          />
          <ion-input
            data-testid="pricing-list-form-valid_until"
            type="date"
            :value="form.validUntil"
            :label="$t('pricing.lists.form.validUntil')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.valid_until"
            :class="invalid(fieldErrors.valid_until)"
            @ion-input="form = { ...form, validUntil: text($event.detail.value) }"
          />
        </div>
        <ion-toggle
          v-if="!priceList"
          data-testid="pricing-list-form-is_default"
          label-placement="start"
          justify="space-between"
          :checked="form.isDefault"
          :disabled="!canBeGeneral"
          :helper-text="$t('pricing.lists.form.isDefaultHelper')"
          @ion-change="form = { ...form, isDefault: !!$event.detail.checked }"
        >
          {{ $t('pricing.lists.form.isDefault') }}
        </ion-toggle>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.pricing-form {
  display: grid;
  gap: 14px;
}
.pricing-form__row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
  gap: 14px;
}
</style>
