<script setup lang="ts">
// TAX-F04/F05/F06/F11 — a new rule, field for field as the old create panel: Country (a Combo over the
// closed ISO list, the old ok-combo: «ZZ» made a rule that matched nothing), Region, Category (a Combo
// searching the server among all the business's), %, Type, Qualification, Exemption reason (only when exempt),
// Regime, Valid from, Valid to, «Root rule (component of)» (the roots the server says the component
// may hang from: ParentRuleSelect) and «Component label». A class that charges no tax pins the rate to
// 0 % (the server refuses any other). The server decides; its refusals stay here under their field.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref } from 'vue';

import { useLocale } from '../composables/useT';
import { countryOptions } from '../lib/countries';
import { categoryCombo } from '../lib/pickers';
import { chargesNoTax, OPERATION_CLASSES, TAX_TYPES } from '../lib/rules';
import type { OperationClass, RuleIn, TaxType } from '../operations';
import ParentRuleSelect from './ParentRuleSelect.vue';

const open = defineModel<boolean>('open', { default: false });

interface RuleForm {
  country_code: string;
  region_code: string;
  tax_category_key: string;
  rate_pct: string;
  tax_type: TaxType;
  operation_class: OperationClass;
  exempt_reason: string;
  regime_key: string;
  valid_from: string;
  valid_to: string;
  parent_id: string;
  component_label: string;
}

const blank = (): RuleForm => ({
  country_code: '',
  region_code: '',
  tax_category_key: '',
  rate_pct: '',
  tax_type: 'vat',
  operation_class: 'subject',
  exempt_reason: '',
  regime_key: '',
  valid_from: '',
  valid_to: '',
  parent_id: '',
  component_label: '',
});

const locale = useLocale();
const form = ref(blank());
const { run, error, pending } = useCommand('tax.rule.create');

/** What the two Combos show: the chosen option (its code or key is what the form keeps). */
const country = ref<ComboOption | null>(null);
const category = ref<ComboOption | null>(null);
/** The category picker searches the server: all the business's categories, not a first page. */
const searchCategories = categoryCombo(useLiveClient());
const countries = computed<ComboOption[]>(() => countryOptions(locale.value).map((option) => ({ id: option.value, label: option.label })));

const noTax = computed(() => chargesNoTax(form.value.operation_class));
const complete = computed(() => form.value.country_code !== '' && form.value.tax_category_key !== '' && form.value.rate_pct.trim() !== '');
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });

function set<K extends keyof RuleForm>(field: K, value: unknown): void {
  form.value = { ...form.value, [field]: value == null ? '' : String(value) };
}

function chooseCountry(option: ComboOption | null): void {
  country.value = option;
  set('country_code', option?.id);
}

function chooseCategory(option: ComboOption | null): void {
  category.value = option;
  set('tax_category_key', option?.id);
}

function reset(): void {
  form.value = blank();
  country.value = null;
  category.value = null;
  error.value = null;
}

/** A class without tax pins the rate to 0; leaving it asks for the rate again, not a 0 nobody typed. */
function setOperationClass(value: unknown): void {
  const next = (value as OperationClass | null) || 'subject';
  const wasNoTax = noTax.value;
  form.value = { ...form.value, operation_class: next };
  if (chargesNoTax(next)) form.value = { ...form.value, rate_pct: '0' };
  else if (wasNoTax) form.value = { ...form.value, rate_pct: '' };
}

/** The rule as the server takes it: the optional fields only when filled, the reason only when exempt. */
function payload(): RuleIn {
  const f = form.value;
  const body: RuleIn = {
    country_code: f.country_code,
    tax_category_key: f.tax_category_key,
    rate_pct: noTax.value ? '0' : f.rate_pct.trim(),
    tax_type: f.tax_type,
    operation_class: f.operation_class,
  };
  const optional: Array<[keyof RuleIn, string]> = [
    ['region_code', f.region_code],
    ['exempt_reason', f.operation_class === 'exempt' ? f.exempt_reason : ''],
    ['regime_key', f.regime_key],
    ['valid_from', f.valid_from],
    ['valid_to', f.valid_to],
    ['parent_id', f.parent_id],
    ['component_label', f.component_label],
  ];
  for (const [key, value] of optional) if (value.trim()) Object.assign(body, { [key]: value.trim() });
  return body;
}

async function save(): Promise<void> {
  try {
    await run(payload());
  } catch {
    return; // `error` holds it and the dialog paints it.
  }
  reset();
  open.value = false;
}

function cancel(): void {
  reset();
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="tax-rule-form"
    :title="$t('tax.rules.form.title')"
    :submit-label="$t('tax.add')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
    @cancel="cancel"
  >
    <template #default="{ fieldErrors }">
      <div class="tax-form">
        <Combo
          testid="tax-rule-form-country_code"
          :model-value="country"
          :options="countries"
          :label="$t('tax.rules.columns.country')"
          :placeholder="$t('tax.rules.form.countryPlaceholder')"
          :error-text="fieldErrors.country_code"
          @update:model-value="chooseCountry"
        />
        <ion-input
          data-testid="tax-rule-form-region_code"
          :value="form.region_code"
          :label="$t('tax.rules.columns.region')"
          :placeholder="$t('tax.rules.form.regionPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="6"
          :debounce="300"
          autocapitalize="characters"
          :error-text="fieldErrors.region_code"
          :class="invalid(fieldErrors.region_code)"
          @ion-input="set('region_code', $event.detail.value)"
        />
        <Combo
          testid="tax-rule-form-tax_category_key"
          :model-value="category"
          :search="searchCategories"
          :label="$t('tax.rules.columns.category')"
          :placeholder="$t('tax.rules.form.categoryPlaceholder')"
          :error-text="fieldErrors.tax_category_key"
          @update:model-value="chooseCategory"
        />
        <ion-input
          data-testid="tax-rule-form-rate_pct"
          type="number"
          inputmode="decimal"
          step="0.01"
          min="0"
          max="100"
          :value="form.rate_pct"
          :label="$t('tax.rules.columns.rate')"
          :placeholder="$t('tax.rules.form.ratePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :disabled="noTax"
          :helper-text="noTax ? $t('tax.rules.form.rateNoTax') : undefined"
          :error-text="fieldErrors.rate_pct"
          :class="invalid(fieldErrors.rate_pct)"
          @ion-input="set('rate_pct', $event.detail.value)"
        />
        <ion-select
          data-testid="tax-rule-form-tax_type"
          :value="form.tax_type"
          :label="$t('tax.rules.columns.type')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.tax_type"
          :class="invalid(fieldErrors.tax_type)"
          @ion-change="set('tax_type', $event.detail.value || 'vat')"
        >
          <ion-select-option
            v-for="type in TAX_TYPES"
            :key="type"
            :value="type"
          >
            {{ $t(`tax.types.${type}`) }}
          </ion-select-option>
        </ion-select>
        <ion-select
          data-testid="tax-rule-form-operation_class"
          :value="form.operation_class"
          :label="$t('tax.rules.columns.qualification')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.operation_class"
          :class="invalid(fieldErrors.operation_class)"
          @ion-change="setOperationClass($event.detail.value)"
        >
          <ion-select-option
            v-for="operationClass in OPERATION_CLASSES"
            :key="operationClass"
            :value="operationClass"
          >
            {{ $t(`tax.classes.${operationClass}`) }}
          </ion-select-option>
        </ion-select>
        <ion-input
          v-if="form.operation_class === 'exempt'"
          data-testid="tax-rule-form-exempt_reason"
          :value="form.exempt_reason"
          :label="$t('tax.rules.form.exemptReason')"
          :placeholder="$t('tax.rules.form.exemptReasonPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="10"
          :error-text="fieldErrors.exempt_reason"
          :class="invalid(fieldErrors.exempt_reason)"
          @ion-input="set('exempt_reason', $event.detail.value)"
        />
        <ion-input
          data-testid="tax-rule-form-regime_key"
          :value="form.regime_key"
          :label="$t('tax.rules.columns.regime')"
          :placeholder="$t('tax.rules.form.regimePlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="10"
          :error-text="fieldErrors.regime_key"
          :class="invalid(fieldErrors.regime_key)"
          @ion-input="set('regime_key', $event.detail.value)"
        />
        <div class="tax-form__pair">
          <ion-input
            data-testid="tax-rule-form-valid_from"
            type="date"
            :value="form.valid_from"
            :label="$t('tax.rules.columns.validFrom')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.valid_from"
            :class="invalid(fieldErrors.valid_from)"
            @ion-input="set('valid_from', $event.detail.value)"
          />
          <ion-input
            data-testid="tax-rule-form-valid_to"
            type="date"
            :value="form.valid_to"
            :label="$t('tax.rules.columns.validTo')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.valid_to"
            :class="invalid(fieldErrors.valid_to)"
            @ion-input="set('valid_to', $event.detail.value)"
          />
        </div>
        <ParentRuleSelect
          :model-value="form.parent_id"
          :country="form.country_code"
          :region="form.region_code"
          :category="form.tax_category_key"
          :rate="noTax ? '0' : form.rate_pct"
          :error-text="fieldErrors.parent_id"
          @update:model-value="set('parent_id', $event)"
        />
        <ion-input
          data-testid="tax-rule-form-component_label"
          :value="form.component_label"
          :label="$t('tax.rules.form.componentLabel')"
          :placeholder="$t('tax.rules.form.componentLabelPlaceholder')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="120"
          :error-text="fieldErrors.component_label"
          :class="invalid(fieldErrors.component_label)"
          @ion-input="set('component_label', $event.detail.value)"
        />
        <p
          class="tax-form__hint"
          data-testid="tax-rule-form-hint"
        >
          {{ $t('tax.rules.form.hint') }}
        </p>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.tax-form {
  display: grid;
  gap: 14px;
}
.tax-form__pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.tax-form__hint {
  margin: 0;
  color: var(--ion-color-medium-shade, #5f5f5f);
  font-size: 0.85rem;
  line-height: 1.45;
}
</style>
