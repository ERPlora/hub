<script setup lang="ts">
// COMBO-F02, F03: the old menu panel as a dialog. «New menu» asks for Name, Kitchen name, Closed price,
// «How is it sold?» (both consequences always shown, the chosen one stressed: the merchant must not
// discover it on an invoice), the VAT category (only eaten in; searched in Taxes), the order on the list
// and «On sale». A menu eaten in without a VAT category, or an amount that is not one, is refused
// before anything is sent. «Menu · {name}» sends only what changed. Refusals stay under their field.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonCheckbox, IonInput, IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchTaxCategories } from '../lib/pickers';
import type { ComboIn, ComboOut, ComboPatchIn, SupplyKind } from '../operations';
import MoneyInput from './MoneyInput.vue';

const props = defineProps<{
  /** The menu being edited; `null` = «New menu». */
  combo: ComboOut | null;
}>();
const open = defineModel<boolean>('open', { default: false });

interface Form {
  name: string;
  kitchenName: string;
  price: string;
  supplyKind: SupplyKind;
  tax: ComboOption | null;
  order: string;
  active: boolean;
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const searchTax = computed(() => searchTaxCategories(client, locale.value));
const creation = useCommand('combo.combo.create');
const update = useCommand('combo.combo.update');
const pending = computed(() => creation.pending.value || update.pending.value);
const error = computed(() => (props.combo ? update.error.value : creation.error.value));
const title = computed(() => (props.combo ? t('combo.form.titleEdit', { name: props.combo.name }) : t('combo.form.titleNew')));

function fromCombo(current: ComboOut | null): Form {
  if (!current) return { name: '', kitchenName: '', price: '', supplyKind: 'service', tax: null, order: '0', active: true };
  return {
    name: current.name,
    kitchenName: current.kitchen_name,
    price: moneyFieldText(current.price, locale.value),
    supplyKind: current.supply_kind,
    tax: current.tax_category_key ? { id: current.tax_category_key, label: current.tax_category_name ?? current.tax_category_key } : null,
    order: String(current.sort_order),
    active: current.is_active,
  };
}

const form = ref<Form>(fromCombo(null));
const tried = ref(false);

watch(
  () => [open.value, props.combo?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    form.value = fromCombo(props.combo);
    tried.value = false;
    creation.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const eatenIn = computed(() => form.value.supplyKind === 'service');
const taxMissing = computed(() => (tried.value && eatenIn.value && !form.value.tax ? t('combo.form.noTaxCategory') : undefined));

/** A whole number as the server takes it; anything else as typed, for the server to refuse. */
function whole(value: string): number {
  const trimmed = value.trim();
  if (!trimmed) return 0;
  return /^\d+$/.test(trimmed) ? Number(trimmed) : (trimmed as unknown as number);
}

function body(price: number): ComboIn {
  const f = form.value;
  return {
    name: f.name.trim(),
    kitchen_name: f.kitchenName.trim(),
    price,
    supply_kind: f.supplyKind,
    tax_category_key: eatenIn.value ? (f.tax?.id ?? null) : null,
    sort_order: whole(f.order),
    is_active: f.active,
  };
}

/** Only what changed (the old module rewrote every field and put a withdrawn menu back on sale). */
function patch(current: ComboOut, full: ComboIn): ComboPatchIn {
  const out: ComboPatchIn = { id: current.id };
  if (full.name !== current.name) out.name = full.name;
  if (full.kitchen_name !== current.kitchen_name) out.kitchen_name = full.kitchen_name;
  if (full.price !== current.price) out.price = full.price;
  if (full.supply_kind !== current.supply_kind) out.supply_kind = full.supply_kind;
  if (full.supply_kind === 'service' && full.tax_category_key !== current.tax_category_key) out.tax_category_key = full.tax_category_key;
  if (full.sort_order !== current.sort_order) out.sort_order = full.sort_order;
  if (full.is_active !== current.is_active) out.is_active = full.is_active;
  return out;
}

async function save(): Promise<void> {
  tried.value = true;
  const price = parseMoney(form.value.price);
  if (!price.ok || taxMissing.value) return;
  const full = body(price.cents ?? 0);
  try {
    if (props.combo) await update.run(patch(props.combo, full));
    else await creation.run(full);
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="combo-menu-form"
    :title="title"
    :submit-label="$t('combo.save')"
    :pending="pending"
    :error="error"
    :submit-disabled="!form.name.trim()"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="combo-menu-form">
        <ion-input
          data-testid="combo-menu-form-name"
          :value="form.name"
          :label="$t('combo.form.name')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :maxlength="255"
          :error-text="fieldErrors.name"
          :class="invalid(fieldErrors.name)"
          @ion-input="form = { ...form, name: text($event.detail.value) }"
        />
        <ion-input
          data-testid="combo-menu-form-kitchen_name"
          :value="form.kitchenName"
          :label="$t('combo.form.kitchenName')"
          :helper-text="$t('combo.form.kitchenNameHelp')"
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
          testid="combo-menu-form-price"
          :label="t('combo.form.price')"
          :helper-text="t('combo.form.priceHelp')"
          :error-text="fieldErrors.price"
          :show-error="tried"
        />
        <ion-select
          data-testid="combo-menu-form-supply_kind"
          :value="form.supplyKind"
          :label="$t('combo.form.supplyLabel')"
          label-placement="floating"
          fill="outline"
          mode="md"
          interface="popover"
          @ion-change="form = { ...form, supplyKind: $event.detail.value === 'goods' ? 'goods' : 'service' }"
        >
          <ion-select-option value="service">
            {{ $t('combo.form.supplyService') }}
          </ion-select-option>
          <ion-select-option value="goods">
            {{ $t('combo.form.supplyGoods') }}
          </ion-select-option>
        </ion-select>
        <p
          class="combo-menu-form__help"
          data-testid="combo-menu-form-help-service"
          :data-active="String(eatenIn)"
        >
          {{ $t('combo.form.supplyService') }}: {{ $t('combo.form.supplyServiceHelp') }}
        </p>
        <p
          class="combo-menu-form__help"
          data-testid="combo-menu-form-help-goods"
          :data-active="String(!eatenIn)"
        >
          {{ $t('combo.form.supplyGoods') }}: {{ $t('combo.form.supplyGoodsHelp') }}
        </p>
        <Combo
          v-if="eatenIn"
          testid="combo-menu-form-tax_category"
          :model-value="form.tax"
          :search="searchTax"
          :label="t('combo.form.taxCategory')"
          :placeholder="t('combo.form.taxCategoryPlaceholder')"
          :helper-text="t('combo.form.taxCategoryHelp')"
          :error-text="taxMissing || fieldErrors.tax_category_key"
          @update:model-value="form = { ...form, tax: $event }"
        />
        <ion-input
          data-testid="combo-menu-form-sort_order"
          type="number"
          inputmode="numeric"
          min="0"
          :value="form.order"
          :label="$t('combo.form.order')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.sort_order"
          :class="invalid(fieldErrors.sort_order)"
          @ion-input="form = { ...form, order: text($event.detail.value) }"
        />
        <ion-checkbox
          data-testid="combo-menu-form-is_active"
          :checked="form.active"
          label-placement="end"
          justify="start"
          @ion-change="form = { ...form, active: $event.detail.checked }"
        >
          {{ $t('combo.form.active') }}
        </ion-checkbox>
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.combo-menu-form {
  display: grid;
  gap: 14px;
}
.combo-menu-form__help {
  margin: 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, #5f5f5f);
}
.combo-menu-form__help[data-active='true'] {
  color: var(--ion-text-color, #1c1b18);
  font-weight: 500;
}
.combo-menu-form__help[data-active='false'] {
  opacity: 0.7;
}
</style>
