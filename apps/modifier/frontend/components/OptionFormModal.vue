<script setup lang="ts">
// MODIFIER-F04 «Añadir, cambiar o quitar las opciones de un grupo»: «Add option» asks for Name, «Kitchen
// ticket name», «Supplement (PLN)» (in the business's currency, its country's, with its decimals; just
// «Supplement» until the business answers; signed: negative is a discount; empty or 0, free), «Own tax category»
// (searched in Taxes; empty = the dish's), «Chosen by default» and Order; Edit opens «Editing option —
// {name}» and sends only what changed with `modifier.option.update` (an emptied tax category sends
// `''`, the dish's again). A supplement that is not an amount is never sent; the server's refusals (a
// taken name, too many defaults, an own line worth nothing) stay under their field.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonToggle } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { useBusinessMoney } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchTaxCategories } from '../lib/pickers';
import type { GroupOut, OptionIn, OptionOut, OptionPatchIn } from '../operations';
import MoneyInput from './MoneyInput.vue';

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
const form = ref<Form>({ name: '', kitchenName: '', price: '', tax: null, isDefault: false, order: '0' });
/** A save was tried: a supplement that is not an amount says so even before leaving the field. */
const tried = ref(false);

function fromOption(option: OptionOut | null): Form {
  if (!option) return { name: '', kitchenName: '', price: '', tax: null, isDefault: false, order: '0' };
  return {
    name: option.name,
    kitchenName: option.kitchen_name,
    price: moneyFieldText(option.price_delta, locale.value, money.value),
    tax: option.tax_category_key ? { id: option.tax_category_key, label: option.tax_category_name ?? option.tax_category_key } : null,
    isDefault: option.is_default,
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
  };
}

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
  };
  for (const key of Object.keys(now) as Array<keyof typeof now>) {
    if (now[key] !== before[key]) (out as Record<string, unknown>)[key] = now[key];
  }
  return out;
}

async function save(): Promise<void> {
  tried.value = true;
  const read = parseMoney(form.value.price, money.value);
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
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="modifier-option-form"
    :title="title"
    :submit-label="option ? $t('modifier.options.form.save') : $t('modifier.options.form.create')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="modifier-form">
        <ion-input
          data-testid="modifier-option-form-name"
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
          testid="modifier-option-form-price_delta"
          :label="money ? $t('modifier.options.form.priceIn', { currency: money.currency }) : $t('modifier.options.form.price')"
          :money="money"
          :helper-text="$t('modifier.options.form.priceHint')"
          :error-text="fieldErrors.price_delta"
          :show-error="tried"
        />
        <Combo
          testid="modifier-option-form-tax_category_key"
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
        <ion-input
          data-testid="modifier-option-form-sort_order"
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
