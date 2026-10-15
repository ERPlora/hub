<script setup lang="ts">
// PRICING-F07, F08: «New price» picks Product or Service, the article (searched in Inventory or in
// Services, by name or SKU), From quantity (1 by default, in the product's unit) and Price (typed as a
// person does); «Add» needs an article and a price. A row's Edit opens «Editing price — {name}» with its
// quantity and price, and «Save» sends only what changed. Refusals stay in the dialog, under their field.
import { Combo, type ComboOption, FormModal } from '@erplora/ui/components';
import { useCommand, useLiveClient } from '@erplora/ui/sdk';
import { IonInput, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useLocale, useT } from '../composables/useT';
import { quantityFieldText, readDecimal } from '../lib/format';
import { moneyFieldText, parseMoney } from '../lib/money';
import { searchProducts, searchServices } from '../lib/pickers';
import type { Kind, PriceItemIn, PriceItemOut, PriceItemPatchIn } from '../operations';
import MoneyInput from './MoneyInput.vue';

const props = withDefaults(defineProps<{ priceListId: string; item?: PriceItemOut | null }>(), { item: null });
const open = defineModel<boolean>('open', { default: false });

interface Form {
  kind: Kind;
  article: ComboOption | null;
  quantity: string;
  price: string;
}

const t = useT();
const locale = useLocale();
const client = useLiveClient();
const search = computed(() => (form.value.kind === 'product' ? searchProducts(client, locale.value) : searchServices(client, locale.value)));
const addition = useCommand('pricing.price_item.add');
const update = useCommand('pricing.price_item.update');
const pending = computed(() => addition.pending.value || update.pending.value);
const error = computed(() => (props.item ? update.error.value : addition.error.value));
const title = computed(() =>
  props.item ? t('pricing.items.form.titleEdit', { name: props.item.name }) : t('pricing.items.form.titleNew'),
);

const form = ref<Form>({ kind: 'product', article: null, quantity: '1', price: '' });
const tried = ref(false);

watch(
  () => [open.value, props.item?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    const item = props.item;
    form.value = item
      ? { kind: item.kind, article: null, quantity: quantityFieldText(item.min_quantity, locale.value), price: moneyFieldText(item.price, locale.value) }
      : { kind: 'product', article: null, quantity: '1', price: '' };
    tried.value = false;
    addition.error.value = null;
    update.error.value = null;
  },
  { immediate: true },
);

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));
const invalid = (message: string | undefined) => ({ 'ion-invalid': !!message, 'ion-touched': !!message });
const cents = computed(() => {
  const read = parseMoney(form.value.price);
  return read.ok ? read.cents : null;
});
/** What the quantity field holds as the server reads it; as typed when unreadable (the server says why). */
const quantity = computed(() => readDecimal(form.value.quantity, 3) ?? form.value.quantity.trim());
const ready = computed(() => cents.value !== null && (props.item !== null || form.value.article !== null));

function setKind(kind: Kind): void {
  if (kind !== form.value.kind) form.value = { ...form.value, kind, article: null };
}

function added(): PriceItemIn {
  const f = form.value;
  const article = f.kind === 'product' ? { product_id: f.article!.id } : { service_id: f.article!.id };
  return { price_list_id: props.priceListId, ...article, min_quantity: quantity.value, price: cents.value! };
}

function patch(item: PriceItemOut): PriceItemPatchIn {
  const out: PriceItemPatchIn = { id: item.id };
  if (cents.value !== item.price) out.price = cents.value!;
  if (Number(quantity.value) !== Number(item.min_quantity)) out.min_quantity = quantity.value;
  return out;
}

async function save(): Promise<void> {
  tried.value = true;
  if (!ready.value) return;
  try {
    if (props.item) await update.run(patch(props.item));
    else await addition.run(added());
  } catch {
    return; // The dialog paints the error; what was typed stays.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="pricing-item-form"
    :title="title"
    :submit-label="item ? $t('pricing.items.form.save') : $t('pricing.items.form.add')"
    :pending="pending"
    :error="error"
    :submit-disabled="!ready"
    @submit="save"
  >
    <template #default="{ fieldErrors }">
      <div class="pricing-form">
        <template v-if="!item">
          <ion-segment
            data-testid="pricing-item-form-kind"
            :value="form.kind"
            :aria-label="t('pricing.items.form.kind')"
            @ion-change="setKind($event.detail.value === 'service' ? 'service' : 'product')"
          >
            <ion-segment-button value="product">
              <ion-label>{{ t('pricing.items.form.product') }}</ion-label>
            </ion-segment-button>
            <ion-segment-button value="service">
              <ion-label>{{ t('pricing.items.form.service') }}</ion-label>
            </ion-segment-button>
          </ion-segment>
          <Combo
            :key="form.kind"
            testid="pricing-item-form-article"
            :model-value="form.article"
            :search="search"
            :label="form.kind === 'product' ? t('pricing.items.form.product') : t('pricing.items.form.service')"
            :placeholder="form.kind === 'product' ? t('pricing.items.form.pickProduct') : t('pricing.items.form.pickService')"
            :clearable="false"
            :error-text="fieldErrors.product || fieldErrors.product_id || fieldErrors.service || fieldErrors.service_id"
            @update:model-value="form = { ...form, article: $event }"
          />
        </template>
        <ion-input
          data-testid="pricing-item-form-min_quantity"
          inputmode="decimal"
          :value="form.quantity"
          :label="$t('pricing.items.form.minQuantity')"
          :helper-text="$t('pricing.items.form.minQuantityHelper')"
          label-placement="floating"
          fill="outline"
          mode="md"
          :error-text="fieldErrors.min_quantity"
          :class="invalid(fieldErrors.min_quantity)"
          @ion-input="form = { ...form, quantity: text($event.detail.value) }"
        />
        <MoneyInput
          testid="pricing-item-form-price"
          :model-value="form.price"
          :label="t('pricing.items.form.price')"
          :error-text="fieldErrors.price"
          :show-error="tried"
          @update:model-value="form = { ...form, price: $event }"
        />
      </div>
    </template>
  </FormModal>
</template>

<style scoped>
.pricing-form {
  display: grid;
  gap: 14px;
}
</style>
