<script setup lang="ts">
// The product form (WORKBOOK «Productos», INVENTORY-F01/F02/F05/F08/F20/F26), the old table's side
// panel as a dialog (FormModal; UI-REQUESTS.md asks for DataTable's side panel). New: Name, SKU,
// Price, «Cost (<currency>)», «Initial stock», «Low stock threshold» (empty = 10), EAN-13, Description, «Type»,
// «Track stock for this item» (physical only; follows the hub until touched), «Unit of measure»,
// «Tax category» (required, none chosen in advance) and «Categories» (when there are any; both search
// the server, TaxCategorySelect and ProductCategoriesField), saved in one go. Editing: the SKU is locked, there is no initial stock nor type, and only what changed is sent
// (the stock is never edited here: it is received or counted). Amounts and quantities are read as
// the person typed them; a refusal stays in the dialog, each message under its field.
import { FormModal } from '@erplora/ui/components';
import { type InputOf, type OutputOf, useCommand } from '@erplora/ui/sdk';
import { IonCheckbox, IonInput, IonNote, IonSelect, IonSelectOption, IonTextarea } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { Unit } from '../composables/useUnits';
import { errorFields } from '../lib/errors';
import { useCurrency } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { readQuantity } from '../lib/quantity';
import MoneyInput from './MoneyInput.vue';
import ProductCategoriesField from './ProductCategoriesField.vue';
import QuantityInput from './QuantityInput.vue';
import TaxCategorySelect from './TaxCategorySelect.vue';

type Product = OutputOf<'inventory.product.list'>['rows'][number];
type UnitCode = Product['unit'];

interface Fields {
  name: string;
  sku: string;
  price: string;
  cost: string;
  initialStock: string;
  threshold: string;
  ean13: string;
  description: string;
  type: Product['product_type'];
  /** The item's own decision; `null` follows the hub. */
  track: boolean | null;
  unit: UnitCode;
  tax: string;
  categories: string[];
}

/** The threshold a product gets when the field is left empty (WORKBOOK INVENTORY-F01). */
const DEFAULT_THRESHOLD = '10';

const props = withDefaults(
  defineProps<{
    product: Product | null;
    units: readonly Unit[];
    /** The business's «Track stock», what an item that has not decided follows. */
    hubTracksStock?: boolean;
  }>(),
  { hubTracksStock: true },
);
const open = defineModel<boolean>('open', { default: false });

const { t, locale } = useT();
const currency = useCurrency();
const create = useCommand('inventory.product.create');
const update = useCommand('inventory.product.update');

const editing = computed(() => props.product !== null);

/** A decimal from the API («10.000») as the field shows it («10»). */
const quantityText = (value: string): string => value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');

function fieldsOf(product: Product | null): Fields {
  return {
    name: product?.name ?? '',
    sku: product?.sku ?? '',
    price: product ? moneyFieldText(product.price, locale.value, currency.value) : '',
    cost: product ? moneyFieldText(product.cost, locale.value, currency.value) : '',
    initialStock: '',
    threshold: product ? quantityText(product.low_stock_threshold) : '',
    ean13: product?.ean13 ?? '',
    description: product?.description ?? '',
    type: product?.product_type ?? 'physical',
    track: product?.track_stock ?? null,
    unit: product?.unit ?? 'ud',
    tax: product?.tax_category_key ?? '',
    categories: [...(product?.category_ids ?? [])],
  };
}

const original = ref<Fields>(fieldsOf(props.product));
const form = ref<Fields>(fieldsOf(props.product));
const tried = ref(false);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    original.value = fieldsOf(props.product);
    form.value = fieldsOf(props.product);
    tried.value = false;
    create.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const command = computed(() => (editing.value ? update : create));
const error = computed(() => command.value.error.value);
const pending = computed(() => command.value.pending.value);
const fields = computed(() => errorFields(error.value));
const invalid = (field: string) => ({ 'ion-invalid': !!fields.value[field], 'ion-touched': !!fields.value[field] });

const title = computed(() =>
  editing.value ? t('inventory.form.editTitle', { name: props.product?.name ?? '' }) : t('inventory.form.newTitle'),
);
/** No tax category, or still the one Taxes deactivated (a «Not configured» product keeps it until changed). */
const taxMissing = computed(() => !form.value.tax || (!!props.product?.needs_tax_setup && form.value.tax === original.value.tax));
const complete = computed(() => !!form.value.name.trim() && !!form.value.sku.trim() && !taxMissing.value);
const tracksNow = computed(() => form.value.track ?? (props.product ? props.product.tracks_stock : props.hubTracksStock));
const step = computed(() => props.units.find((unit) => unit.code === form.value.unit)?.increment);
/** Each unit by the name the API gives it, which already carries its code («Unit (ud)»). */
const unitOptions = computed(() =>
  props.units.length ? props.units.map((unit) => ({ code: unit.code, label: unit.name })) : [{ code: form.value.unit, label: form.value.unit }],
);

function set<K extends keyof Fields>(key: K, value: Fields[K]): void {
  form.value = { ...form.value, [key]: value };
}

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

/** The fields read as the API takes them, or `null` when an amount or a quantity cannot be read. */
function read() {
  const price = parseMoney(form.value.price, currency.value);
  const cost = parseMoney(form.value.cost, currency.value);
  const initial = readQuantity(form.value.initialStock);
  const threshold = readQuantity(form.value.threshold);
  if (!price.ok || !cost.ok || !initial.ok || !threshold.ok) return null;
  return { price: price.cents ?? 0, cost: cost.cents ?? 0, initial: initial.value ?? '0', threshold: threshold.value ?? DEFAULT_THRESHOLD };
}

async function save(): Promise<void> {
  tried.value = true;
  const values = read();
  if (!values || !complete.value) return;
  const now = form.value;
  try {
    if (props.product) {
      const was = original.value;
      const wasRead = { price: props.product.price, cost: props.product.cost, threshold: quantityText(props.product.low_stock_threshold) };
      const patch: InputOf<'inventory.product.update'> = {
        id: props.product.id,
        ...(now.name.trim() !== was.name ? { name: now.name.trim() } : {}),
        ...(values.price !== wasRead.price ? { price: values.price } : {}),
        ...(values.cost !== wasRead.cost ? { cost: values.cost } : {}),
        ...(values.threshold !== wasRead.threshold ? { low_stock_threshold: values.threshold } : {}),
        ...(now.ean13.trim() !== was.ean13 ? { ean13: now.ean13.trim() } : {}),
        ...(now.description !== was.description ? { description: now.description } : {}),
        ...(now.tax !== was.tax ? { tax_category_key: now.tax } : {}),
        ...(now.unit !== was.unit ? { unit: now.unit } : {}),
        ...(now.track !== was.track && now.track !== null ? { track_stock: now.track } : {}),
        ...(now.categories.join() !== was.categories.join() ? { category_ids: now.categories } : {}),
      };
      await update.run(patch);
    } else {
      await create.run({
        name: now.name.trim(),
        sku: now.sku.trim(),
        price: values.price,
        cost: values.cost,
        tax_category_key: now.tax,
        initial_stock: values.initial,
        low_stock_threshold: values.threshold,
        ean13: now.ean13.trim() || null,
        description: now.description,
        product_type: now.type,
        unit: now.unit,
        track_stock: now.type === 'service' ? null : now.track,
        category_ids: now.categories,
      });
    }
  } catch {
    return; // the dialog paints the error and stays open.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :title="title"
    testid="inventory-product-form"
    :submit-label="pending ? $t('inventory.common.saving') : editing ? $t('inventory.common.saveChanges') : $t('inventory.common.save')"
    :cancel-label="editing ? $t('inventory.form.cancelEdit') : $t('inventory.common.cancel')"
    :pending="pending"
    :error="error"
    :submit-disabled="!complete"
    @submit="save"
  >
    <div class="product-form">
      <ion-input
        data-testid="inventory-product-name"
        :model-value="form.name"
        :label="$t('inventory.form.name')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="200"
        :error-text="fields.name"
        :class="invalid('name')"
        @update:model-value="set('name', text($event))"
      />
      <ion-input
        data-testid="inventory-product-sku"
        :model-value="form.sku"
        :label="$t('inventory.form.sku')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="64"
        :disabled="editing"
        :helper-text="editing ? $t('inventory.form.skuIdentity') : undefined"
        :error-text="fields.sku"
        :class="invalid('sku')"
        @update:model-value="set('sku', text($event))"
      />
      <MoneyInput
        v-model="form.price"
        testid="inventory-product-price"
        :label="$t('inventory.form.price')"
        :error-text="fields.price"
        :show-error="tried"
      />
      <MoneyInput
        v-model="form.cost"
        testid="inventory-product-cost"
        :label="currency ? $t('inventory.form.costIn', { currency }) : $t('inventory.form.cost')"
        :error-text="fields.cost"
        :show-error="tried"
      />
      <QuantityInput
        v-if="!editing"
        v-model="form.initialStock"
        testid="inventory-product-initial-stock"
        :label="$t('inventory.form.initialStock')"
        :unit="form.unit"
        :step="step"
        :error-text="fields.initial_stock"
        :show-error="tried"
      />
      <QuantityInput
        v-model="form.threshold"
        testid="inventory-product-threshold"
        :label="$t('inventory.form.threshold')"
        :unit="form.unit"
        :step="step"
        :error-text="fields.low_stock_threshold"
        :show-error="tried"
      />
      <ion-input
        data-testid="inventory-product-ean13"
        :model-value="form.ean13"
        :label="$t('inventory.form.ean13')"
        label-placement="floating"
        fill="outline"
        mode="md"
        inputmode="numeric"
        :maxlength="13"
        :error-text="fields.ean13"
        :class="invalid('ean13')"
        @update:model-value="set('ean13', text($event))"
      />
      <ion-textarea
        data-testid="inventory-product-description"
        :model-value="form.description"
        :label="$t('inventory.form.description')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :auto-grow="true"
        :maxlength="2000"
        :error-text="fields.description"
        :class="invalid('description')"
        @update:model-value="set('description', text($event))"
      />
      <ion-select
        v-if="!editing"
        data-testid="inventory-product-type"
        :model-value="form.type"
        :label="$t('inventory.form.type')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        @update:model-value="set('type', $event === 'service' ? 'service' : 'physical')"
      >
        <ion-select-option value="physical">
          {{ $t('inventory.form.physical') }}
        </ion-select-option>
        <ion-select-option value="service">
          {{ $t('inventory.form.service') }}
        </ion-select-option>
      </ion-select>
      <div
        v-if="form.type !== 'service'"
        class="product-form__track"
      >
        <ion-checkbox
          data-testid="inventory-product-track-stock"
          label-placement="end"
          justify="start"
          :model-value="tracksNow"
          @update:model-value="set('track', !!$event)"
        >
          <span>{{ $t('inventory.form.trackStock') }}</span>
        </ion-checkbox>
        <ion-note
          v-if="form.track !== true"
          data-testid="inventory-product-track-note"
        >
          {{ form.track === null ? $t('inventory.form.trackInherit') : $t('inventory.form.trackOff') }}
        </ion-note>
      </div>
      <ion-select
        data-testid="inventory-product-unit"
        :model-value="form.unit"
        :label="$t('inventory.form.unit')"
        label-placement="floating"
        fill="outline"
        mode="md"
        interface="popover"
        :error-text="fields.unit"
        :class="invalid('unit')"
        @update:model-value="set('unit', (text($event) || 'ud') as UnitCode)"
      >
        <ion-select-option
          v-for="option in unitOptions"
          :key="option.code"
          :value="option.code"
        >
          {{ option.label }}
        </ion-select-option>
      </ion-select>
      <TaxCategorySelect
        testid="inventory-product-tax"
        :model-value="form.tax"
        :mark-missing="editing"
        :error-text="fields.tax_category_key"
        @update:model-value="set('tax', $event)"
      />
      <ProductCategoriesField
        testid="inventory-product-categories"
        :model-value="form.categories"
        :error-text="fields.category_ids"
        @update:model-value="set('categories', $event)"
      />
    </div>
  </FormModal>
</template>

<style scoped>
.product-form {
  display: grid;
  gap: 16px;
}

.product-form__track {
  display: grid;
  gap: 4px;
}

.product-form__track ion-note {
  font-size: 0.8rem;
}
</style>
