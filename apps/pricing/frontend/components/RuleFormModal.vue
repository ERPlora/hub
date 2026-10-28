<script setup lang="ts">
// PRICING-F10, F11: «New discount rule» asks for Code and Name, the Type with its value (Percent; Amount
// per unit, typed as a person does; Buy and Free units; or up to 10 tiers «from quantity, percent»), what
// it Applies to (Everything, All products, All services, or one category, product or service searched in
// Inventory or Services), and Customer group (empty = every customer), Minimum quantity, From, Until and
// Priority (100). A row's Edit opens «Editing rule — {name}» and «Save» sends only what changed: a new
// type with its value, a new scope with its target (the server empties the old ones). Refusals stay in
// the dialog, under their field. The amount, and the catalog prices beside the products and services, are in
// the business's currency (its country's; a bare figure until it answers, and then an untouched amount takes its
// decimals).
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonButton, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/format';
import { quantityFieldText, readDecimal } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchCategories, searchGroups, searchProducts, searchServices } from '../lib/pickers';
import { groupName } from '../lib/rules';
import type { RuleIn, RuleOut, RuleScope, RuleType } from '../operations';
import MoneyInput from './MoneyInput.vue';

const TYPES: readonly RuleType[] = ['percent', 'fixed', 'buy_x_get_y', 'tiered'];
const SCOPES: readonly RuleScope[] = ['all', 'products', 'services', 'category', 'product', 'service'];
/** The scopes that name one target, and the field of its id. */
const TARGETS: Partial<Record<RuleScope, 'category_id' | 'product_id' | 'service_id'>> = {
  category: 'category_id',
  product: 'product_id',
  service: 'service_id',
};
const MAX_TIERS = 10;

const props = withDefaults(defineProps<{ rule?: RuleOut | null }>(), { rule: null });
const open = defineModel<boolean>('open', { default: false });

interface TierForm {
  min: string;
  percent: string;
}

interface Form {
  code: string;
  name: string;
  type: RuleType;
  percent: string;
  amount: string;
  buy: string;
  get: string;
  tiers: TierForm[];
  scope: RuleScope;
  target: ComboOption | null;
  group: ComboOption | null;
  minQuantity: string;
  validFrom: string;
  validUntil: string;
  priority: string;
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const money = useBusinessMoney();
const searchGroup = searchGroups(client);
const searchTarget = computed(() => {
  if (form.value.scope === 'category') return searchCategories(client);
  if (form.value.scope === 'product') return searchProducts(client, locale.value, money.value);
  return searchServices(client, locale.value, money.value);
});
const creation = useCommand('pricing.rule.create');
const update = useCommand('pricing.rule.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.rule ? update.error.value : creation.error.value));
const title = computed(() => (props.rule ? t('pricing.rules.form.titleEdit', { name: props.rule.name }) : t('pricing.rules.form.titleNew')));

const decimalText = (value: string | null): string => (value === null ? '' : quantityFieldText(value, locale.value));

function blank(): Form {
  return {
    code: '',
    name: '',
    type: 'percent',
    percent: '',
    amount: '',
    buy: '',
    get: '',
    tiers: [{ min: '', percent: '' }],
    scope: 'all',
    target: null,
    group: null,
    minQuantity: '',
    validFrom: '',
    validUntil: '',
    priority: '100',
  };
}

function fromRule(rule: RuleOut): Form {
  const names: Partial<Record<RuleScope, [string | null, string | null]>> = {
    category: [rule.category_id, rule.category_name],
    product: [rule.product_id, rule.product_name],
    service: [rule.service_id, rule.service_name],
  };
  const [targetId, targetName] = names[rule.applies_to] ?? [null, null];
  return {
    code: rule.code,
    name: rule.name,
    type: rule.rule_type,
    percent: decimalText(rule.percent),
    amount: rule.amount === null ? '' : moneyFieldText(rule.amount, locale.value, money.value),
    buy: rule.buy_quantity === null ? '' : String(rule.buy_quantity),
    get: rule.get_quantity === null ? '' : String(rule.get_quantity),
    tiers: rule.tiers.length
      ? rule.tiers.map((tier) => ({ min: decimalText(tier.min_quantity), percent: decimalText(tier.percent) }))
      : [{ min: '', percent: '' }],
    scope: rule.applies_to,
    target: targetId ? { id: targetId, label: targetName ?? t('pricing.none') } : null,
    group: rule.customer_group_id ? { id: rule.customer_group_id, label: groupName(rule.customer_group_id, rule.customer_group_name, t) } : null,
    minQuantity: decimalText(rule.min_quantity),
    validFrom: rule.valid_from ?? '',
    validUntil: rule.valid_until ?? '',
    priority: String(rule.priority),
  };
}

const form = ref<Form>(blank());
const tried = ref(false);

watch(
  () => [open.value, props.rule?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = props.rule ? fromRule(props.rule) : blank();
    tried.value = false;
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

// The business answers (or its currency changes) with the form open: an amount per unit the person has not touched
// is rewritten from the rule with the currency's decimals («1.50» → «150» in yen); what they typed stays as typed,
// read in the new currency when they save (the field says so when it cannot be).
watch(money, (now, before) => {
  if (!open.value) return;
  const amount = props.rule?.amount ?? null;
  if (form.value.amount !== moneyFieldText(amount, locale.value, before)) return;
  form.value = { ...form.value, amount: moneyFieldText(amount, locale.value, now) };
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** A decimal as the server reads it; as typed when unreadable (the server says why under its field). */
const decimal = (value: string, places: number): string => readDecimal(value, places) ?? value.trim();
/** A whole number as the server reads it; as typed when it is not one (the server says why). */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));
const day = (value: string): string | null => value.trim() || null;
const cents = (value: string): number | null => {
  const read = parseMoney(value, money.value);
  return read.ok ? read.cents : null;
};

/** The value(s) of the form's type, as the server takes them. */
function valueOf(f: Form): Partial<RuleIn> {
  if (f.type === 'percent') return { percent: decimal(f.percent, 2) };
  if (f.type === 'fixed') return { amount: cents(f.amount) ?? 0 };
  if (f.type === 'buy_x_get_y') return { buy_quantity: whole(f.buy), get_quantity: whole(f.get) };
  return { tiers: f.tiers.map((tier) => ({ min_quantity: decimal(tier.min, 3), percent: decimal(tier.percent, 2) })) };
}

/** The whole rule the form says, as the create takes it. */
function body(f: Form): RuleIn {
  const target = TARGETS[f.scope];
  return {
    code: f.code.trim(),
    name: f.name.trim(),
    rule_type: f.type,
    ...valueOf(f),
    applies_to: f.scope,
    ...(target ? { [target]: f.target?.id ?? null } : {}),
    customer_group_id: f.group?.id ?? null,
    min_quantity: f.minQuantity.trim() ? decimal(f.minQuantity, 3) : null,
    valid_from: day(f.validFrom),
    valid_until: day(f.validUntil),
    priority: whole(f.priority),
  };
}

const filled = (value: string): boolean => value.trim() !== '';
const ready = computed(() => {
  const f = form.value;
  const valued = {
    percent: filled(f.percent),
    fixed: (cents(f.amount) ?? 0) > 0,
    buy_x_get_y: filled(f.buy) && filled(f.get),
    tiered: f.tiers.length > 0 && f.tiers.every((tier) => filled(tier.min) && filled(tier.percent)),
  }[f.type];
  return filled(f.code) && filled(f.name) && valued && (!TARGETS[f.scope] || f.target !== null);
});

function setScope(scope: RuleScope): void {
  if (scope !== form.value.scope) form.value = { ...form.value, scope, target: null };
}

function setTier(index: number, change: Partial<TierForm>): void {
  form.value = { ...form.value, tiers: form.value.tiers.map((tier, i) => (i === index ? { ...tier, ...change } : tier)) };
}

function addTier(): void {
  form.value = { ...form.value, tiers: [...form.value.tiers, { min: '', percent: '' }] };
}

function removeTier(index: number): void {
  form.value = { ...form.value, tiers: form.value.tiers.filter((_, i) => i !== index) };
}

/** Only the keys whose value the form changed (a new type brings its value, a new scope its target). */
function patch(rule: RuleOut): Record<string, unknown> {
  const now = body(form.value) as unknown as Record<string, unknown>;
  const before = body(fromRule(rule)) as unknown as Record<string, unknown>;
  const out: Record<string, unknown> = { id: rule.id };
  for (const [key, value] of Object.entries(now)) {
    if (JSON.stringify(value) !== JSON.stringify(before[key])) out[key] = value;
  }
  return out;
}

async function save(): Promise<void> {
  tried.value = true;
  if (!ready.value) return;
  try {
    if (props.rule) await update.run(patch(props.rule));
    else await creation.run(body(form.value));
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="pricing-rule-form"
    :title="title"
    :submit-label="rule ? $t('pricing.rules.form.save') : $t('pricing.rules.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!ready"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="pricing-form">
        <div class="pricing-form__row">
          <ion-input
            data-testid="pricing-rule-form-code"
            :value="form.code"
            :label="$t('pricing.rules.form.code')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="50"
            :error-text="fieldErrors.code"
            :class="invalid(fieldErrors.code)"
            @ion-input="form = { ...form, code: text($event.detail.value) }"
          />
          <ion-input
            data-testid="pricing-rule-form-name"
            :value="form.name"
            :label="$t('pricing.rules.form.name')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :maxlength="200"
            :error-text="fieldErrors.name"
            :class="invalid(fieldErrors.name)"
            @ion-input="form = { ...form, name: text($event.detail.value) }"
          />
        </div>
        <ion-select
          data-testid="pricing-rule-form-rule_type"
          :value="form.type"
          :label="$t('pricing.rules.form.type')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.rule_type"
          @ion-change="form = { ...form, type: $event.detail.value as RuleType }"
        >
          <ion-select-option
            v-for="type in TYPES"
            :key="type"
            :value="type"
          >
            {{ t(`pricing.rules.type.${type}`) }}
          </ion-select-option>
        </ion-select>
        <ion-input
          v-if="form.type === 'percent'"
          data-testid="pricing-rule-form-percent"
          inputmode="decimal"
          :value="form.percent"
          :label="$t('pricing.rules.form.percent')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.percent"
          :class="invalid(fieldErrors.percent)"
          @ion-input="form = { ...form, percent: text($event.detail.value) }"
        />
        <MoneyInput
          v-else-if="form.type === 'fixed'"
          testid="pricing-rule-form-amount"
          :model-value="form.amount"
          :money="money"
          :label="t('pricing.rules.form.amount')"
          :error-text="fieldErrors.amount"
          :show-error="tried"
          @update:model-value="form = { ...form, amount: $event }"
        />
        <div
          v-else-if="form.type === 'buy_x_get_y'"
          class="pricing-form__row"
        >
          <ion-input
            data-testid="pricing-rule-form-buy_quantity"
            type="number"
            inputmode="numeric"
            min="1"
            :value="form.buy"
            :label="$t('pricing.rules.form.buy')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.buy_quantity"
            :class="invalid(fieldErrors.buy_quantity)"
            @ion-input="form = { ...form, buy: text($event.detail.value) }"
          />
          <ion-input
            data-testid="pricing-rule-form-get_quantity"
            type="number"
            inputmode="numeric"
            min="1"
            :value="form.get"
            :label="$t('pricing.rules.form.get')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.get_quantity"
            :class="invalid(fieldErrors.get_quantity)"
            @ion-input="form = { ...form, get: text($event.detail.value) }"
          />
        </div>
        <fieldset
          v-else
          class="pricing-form__tiers"
          data-testid="pricing-rule-form-tiers"
        >
          <legend>{{ t('pricing.rules.form.tiers') }}</legend>
          <div
            v-for="(tier, index) in form.tiers"
            :key="index"
            class="pricing-form__tier"
          >
            <ion-input
              :data-testid="`pricing-rule-form-tier-${index}-min_quantity`"
              inputmode="decimal"
              :value="tier.min"
              :label="$t('pricing.rules.form.tierFrom')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :error-text="fieldErrors[`tiers.${index}.min_quantity`]"
              :class="invalid(fieldErrors[`tiers.${index}.min_quantity`])"
              @ion-input="setTier(index, { min: text($event.detail.value) })"
            />
            <ion-input
              :data-testid="`pricing-rule-form-tier-${index}-percent`"
              inputmode="decimal"
              :value="tier.percent"
              :label="$t('pricing.rules.form.tierPercent')"
              label-placement="floating"
              fill="outline"
              mode="md"
              :error-text="fieldErrors[`tiers.${index}.percent`]"
              :class="invalid(fieldErrors[`tiers.${index}.percent`])"
              @ion-input="setTier(index, { percent: text($event.detail.value) })"
            />
            <ion-button
              v-if="form.tiers.length > 1"
              :data-testid="`pricing-rule-form-tier-${index}-remove`"
              fill="clear"
              color="danger"
              @click="removeTier(index)"
            >
              {{ t('pricing.rules.form.removeTier') }}
            </ion-button>
          </div>
          <p
            v-if="fieldErrors.tiers"
            class="pricing-form__error"
          >
            {{ fieldErrors.tiers }}
          </p>
          <ion-button
            v-if="form.tiers.length < MAX_TIERS"
            data-testid="pricing-rule-form-add-tier"
            fill="outline"
            size="small"
            @click="addTier"
          >
            {{ t('pricing.rules.form.addTier') }}
          </ion-button>
        </fieldset>
        <ion-select
          data-testid="pricing-rule-form-applies_to"
          :value="form.scope"
          :label="$t('pricing.rules.form.appliesTo')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          :error-text="fieldErrors.applies_to"
          @ion-change="setScope($event.detail.value as RuleScope)"
        >
          <ion-select-option
            v-for="scope in SCOPES"
            :key="scope"
            :value="scope"
          >
            {{ t(`pricing.rules.scope.${scope}`) }}
          </ion-select-option>
        </ion-select>
        <Combo
          v-if="TARGETS[form.scope]"
          :key="form.scope"
          testid="pricing-rule-form-target"
          :model-value="form.target"
          :search="searchTarget"
          :label="t(`pricing.rules.form.${form.scope}`)"
          :clearable="false"
          :error-text="fieldErrors[form.scope] || fieldErrors[`${form.scope}_id`]"
          @update:model-value="form = { ...form, target: $event }"
        />
        <Combo
          testid="pricing-rule-form-group"
          :model-value="form.group"
          :search="searchGroup"
          :label="t('pricing.rules.form.group')"
          :placeholder="t('pricing.rules.form.everybody')"
          clearable
          :error-text="fieldErrors.customer_group_id || fieldErrors.customer_group"
          @update:model-value="form = { ...form, group: $event }"
        />
        <div class="pricing-form__row">
          <ion-input
            data-testid="pricing-rule-form-min_quantity"
            inputmode="decimal"
            :value="form.minQuantity"
            :label="$t('pricing.rules.form.minQuantity')"
            :helper-text="$t('pricing.rules.form.unitsHelper')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.min_quantity"
            :class="invalid(fieldErrors.min_quantity)"
            @ion-input="form = { ...form, minQuantity: text($event.detail.value) }"
          />
          <ion-input
            data-testid="pricing-rule-form-priority"
            type="number"
            inputmode="numeric"
            min="0"
            :value="form.priority"
            :label="$t('pricing.rules.form.priority')"
            :helper-text="$t('pricing.rules.form.priorityHelper')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.priority"
            :class="invalid(fieldErrors.priority)"
            @ion-input="form = { ...form, priority: text($event.detail.value) }"
          />
        </div>
        <div class="pricing-form__row">
          <ion-input
            data-testid="pricing-rule-form-valid_from"
            type="date"
            :value="form.validFrom"
            :label="$t('pricing.rules.form.validFrom')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.valid_from"
            :class="invalid(fieldErrors.valid_from)"
            @ion-input="form = { ...form, validFrom: text($event.detail.value) }"
          />
          <ion-input
            data-testid="pricing-rule-form-valid_until"
            type="date"
            :value="form.validUntil"
            :label="$t('pricing.rules.form.validUntil')"
            label-placement="floating"
            fill="outline"
            mode="md"
            :error-text="fieldErrors.valid_until"
            :class="invalid(fieldErrors.valid_until)"
            @ion-input="form = { ...form, validUntil: text($event.detail.value) }"
          />
        </div>
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
.pricing-form__tiers {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 10px 12px 12px;
  border: 1px solid var(--ion-border-color, #e7e2d6);
  border-radius: 8px;
}
.pricing-form__tiers legend {
  padding: 0 4px;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #5c594f);
}
.pricing-form__tier {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(8rem, 1fr));
  gap: 10px;
  align-items: start;
}
.pricing-form__error {
  margin: 0;
  font-size: 0.8rem;
  color: var(--ion-color-danger, #c5000f);
}
</style>
