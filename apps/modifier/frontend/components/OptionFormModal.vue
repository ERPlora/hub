<script setup lang="ts">
// MODIFIER-F04 «Add, change or remove the options of a group»: «Add option» asks for Name, «Kitchen ticket name»,
// «Supplement (PLN)» (in the business's currency, its country's, with its decimals; just «Supplement» until the
// business answers; signed: negative is a discount; empty or 0, free), «Own tax category» (searched in Taxes; empty =
// the dish's), «Chosen by default», the allergens it adds to the dish (MODIFIER-F11) and Order; Edit opens «Editing
// option — {name}» and sends only what changed with `modifier.option.update` (an emptied tax category sends `''`, the
// dish's again). «Create» / «Save» wait in grey until the business has answered its money (the supplement is read in
// it; hub#918). A supplement that is not an amount is never sent; the server's refusals (a taken name, too many
// defaults, an own line worth nothing, an allergen off the list) stay under their field.
import {
  AllergenSelect,
  type AllergenCode,
  Combo,
  type ComboOption,
  FormModal,
  MoneyInput,
  moneyFieldText,
  parseMoney,
} from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import BusinessMoneyError from '../../../../base/frontend/components/BusinessMoneyError.vue';
import { useGroupChange } from '../../../../base/frontend/lib/group-change';
import { useUnsavedFormOnOpen } from '../../../../base/frontend/lib/unsaved-changes';
import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/format';
import { searchTaxCategories } from '../lib/pickers';
import type { GroupOut, OptionIn, OptionOut, OptionPatchIn } from '../operations';

const props = defineProps<{
  /** The group the option belongs to. */
  group: Pick<GroupOut, 'id' | 'name'>;
  /** The option being edited; `null` = «Add option». */
  option: OptionOut | null;
}>();

const open = defineModel<boolean>('open', { default: false });

interface Form {
  name: string;
  kitchenName: string;
  price: string;
  tax: ComboOption | null;
  isDefault: boolean;
  allergens: AllergenCode[];
  order: string;
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const money = useBusinessMoney();
const creation = useCommand('modifier.option.create');
const update = useCommand('modifier.option.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.option ? update.error.value : creation.error.value));
const title = computed(() =>
  props.option ? t('modifier.options.form.titleEdit', { name: props.option.name }) : t('modifier.options.form.titleNew'),
);
const searchTax = computed(() => searchTaxCategories(client, t, locale.value));
const form = ref<Form>({ name: '', kitchenName: '', price: '', tax: null, isDefault: false, allergens: [], order: '0' });
/** The fourteen are refused as one group: each mark tells the window, which takes their refusal away. */
const allergensChanged = useGroupChange('allergensGroup');
/** A save was tried: a supplement that is not an amount says so even before leaving the field. */
const tried = ref(false);

function setAllergens(allergens: AllergenCode[]): void {
  form.value = { ...form.value, allergens };
  allergensChanged();
}

function fromOption(option: OptionOut | null): Form {
  if (!option) return { name: '', kitchenName: '', price: '', tax: null, isDefault: false, allergens: [], order: '0' };
  return {
    name: option.name,
    kitchenName: option.kitchen_name,
    price: moneyFieldText(option.price_delta, locale.value, money.value),
    tax: option.tax_category_key ? { id: option.tax_category_key, label: option.tax_category_name ?? option.tax_category_key } : null,
    isDefault: option.is_default,
    allergens: [...option.allergens],
    order: String(option.sort_order),
  };
}

watch(
  () => [open.value, props.option?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromOption(props.option);
    tried.value = false;
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

// The business answers (or its currency changes) with the form open: a supplement the person has not touched is
// rewritten from the option with the currency's decimals («1.50» → «150» in yen); what they typed stays as typed,
// read in the new currency when they save (the field says so when it cannot be).
watch(money, (now, before) => {
  if (!open.value) return;
  const written = props.option ? moneyFieldText(props.option.price_delta, locale.value, before) : '';
  if (form.value.price !== written) return;
  form.value = { ...form.value, price: props.option ? moneyFieldText(props.option.price_delta, locale.value, now) : '' };
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
/** A whole number as the server takes it; anything else as typed, for the server to refuse. */
const whole = (value: string): number => (/^\d+$/.test(value.trim()) ? Number(value.trim()) : (value.trim() as unknown as number));

function fields(cents: number): Required<Omit<OptionIn, 'group' | 'group_id'>> {
  const f = form.value;
  return {
    name: f.name.trim(),
    kitchen_name: f.kitchenName.trim(),
    price_delta: cents,
    tax_category_key: f.tax?.id ?? '',
    is_default: f.isDefault,
    sort_order: whole(f.order || '0'),
    allergens: f.allergens,
  };
}

/** Two values of a field are the same; two lists of allergens, when they hold the same codes in the same order. */
const same = (a: unknown, b: unknown): boolean => (Array.isArray(a) && Array.isArray(b) ? a.join() === b.join() : a === b);

function patch(option: OptionOut, cents: number): OptionPatchIn {
  const out: OptionPatchIn = { id: option.id };
  const now = fields(cents);
  const before = {
    name: option.name,
    kitchen_name: option.kitchen_name,
    price_delta: option.price_delta,
    tax_category_key: option.tax_category_key ?? '',
    is_default: option.is_default,
    sort_order: option.sort_order,
    allergens: option.allergens,
  };
  for (const key of Object.keys(now) as Array<keyof typeof now>) {
    if (!same(now[key], before[key])) (out as Record<string, unknown>)[key] = now[key];
  }
  return out;
}

async function save(): Promise<void> {
  tried.value = true;
  // No supplement is read before the business answers its money: «150» would be read with two decimals, whatever its
  // currency counts (in yen, 15000; hub#918).
  const business = money.value;
  if (!business) return;
  const read = parseMoney(form.value.price, { money: business, signed: true });
  if (!read.ok) return; // The field says why.
  const cents = read.cents ?? 0;
  try {
    if (props.option) await update.run(patch(props.option, cents));
    else await creation.run({ group_id: props.group.id, ...fields(cents) });
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}

// An untouched supplement follows the business's money when it answers after the window opened: that is no change.
const canDismiss = useUnsavedFormOnOpen(
  'modifier-option-form',
  () => {
    const stored = props.option ? moneyFieldText(props.option.price_delta, locale.value, money.value) : '';
    return { ...form.value, price: form.value.price === stored ? null : form.value.price };
  },
  open,
);
</script>

<template>
  <FormModal
    v-model:open="open"
    :can-dismiss="canDismiss"
    testid="modifier-option-form"
    :title="title"
    :submit-label="option ? $t('modifier.options.form.save') : $t('modifier.options.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!money || !form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="modifier-form">
        <BusinessMoneyError />
        <ion-input
          data-testid="modifier-option-form-name"
          name="name"
          :value="form.name"
          :label="$t('modifier.options.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-input
          data-testid="modifier-option-form-kitchen_name"
          name="kitchen_name"
          :value="form.kitchenName"
          :label="$t('modifier.options.form.kitchenName')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.kitchen_name"
          :class="invalid(fieldErrors.kitchen_name)"
          @ion-input="form = { ...form, kitchenName: text($event.detail.value) }"
        />
        <MoneyInput
          v-model="form.price"
          signed
          testid="modifier-option-form-price_delta"
          name="price_delta"
          :label="money ? $t('modifier.options.form.priceIn', { currency: money.currency }) : $t('modifier.options.form.price')"
          :money="money"
          :helper-text="$t('modifier.options.form.priceHint')"
          :error-text="fieldErrors.price_delta"
          :show-error="tried"
        />
        <Combo
          testid="modifier-option-form-tax_category_key"
          name="tax_category_key"
          :model-value="form.tax"
          :search="searchTax"
          :label="$t('modifier.options.form.tax')"
          :placeholder="$t('modifier.options.form.noTax')"
          :helper-text="$t('modifier.options.form.taxHint')"
          :error-text="fieldErrors.tax_category_key"
          @update:model-value="form = { ...form, tax: $event }"
        />
        <ion-toggle
          data-testid="modifier-option-form-is_default"
          name="is_default"
          :checked="form.isDefault"
          label-placement="end"
          justify="start"
          @ion-change="form = { ...form, isDefault: $event.detail.checked }"
        >
          {{ $t('modifier.options.form.default') }}
        </ion-toggle>
        <p
          v-if="fieldErrors.is_default"
          class="modifier-form__error"
          data-testid="modifier-option-form-is_default-error"
        >
          {{ fieldErrors.is_default }}
        </p>
        <AllergenSelect
          ref="allergensGroup"
          name="allergens"
          testid="modifier-option-form-allergens"
          :model-value="form.allergens"
          :label="$t('modifier.options.form.allergens')"
          :helper-text="$t('modifier.options.form.allergensHint')"
          :error-text="fieldErrors.allergens"
          :disabled="pending"
          @update:model-value="setAllergens"
        />
        <ion-input
          data-testid="modifier-option-form-sort_order"
          name="sort_order"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form.order"
          :label="$t('modifier.options.form.order')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.sort_order"
          :class="invalid(fieldErrors.sort_order)"
          @ion-input="form = { ...form, order: text($event.detail.value) }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.modifier-form {
  display: grid;
  gap: 14px;
}
.modifier-form__error {
  margin: -8px 0 0;
  font-size: 0.8rem;
  color: var(--ion-color-danger, #c5000f);
}
</style>
