<script setup lang="ts">
// The stock dialogs of a product (WORKBOOK «Recepción», «Recuento», «Baja», INVENTORY-F13/F14/F15),
// the old receive and count modals plus the write-off (waste, breakage, own consumption):
//   - receive: «Current stock», «Quantity received», «Unit cost (<currency>)» → `inventory.stock.receive`;
//   - count: «Current stock», «Difference» once there is a figure, «Counted stock» (the total, not
//     the difference), «Reason (required)» → `inventory.stock.count`;
//   - write_off: the quantity and its reason → `inventory.stock.write_off`.
// The action is off until it can be taken, with the note of what is missing; quantities go in the
// product's unit (its step stated); a refusal stays in the dialog under its field.
import { FormModal } from '@erplora/ui/components';
import { type OutputOf, useCommand } from '@erplora/ui/sdk';
import { IonInput, IonItem, IonLabel, IonList, IonNote } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import { useT } from '../composables/useT';
import type { Unit } from '../composables/useUnits';
import { errorFields } from '../lib/errors';
import { formatQuantity, formatSignedQuantity, useBusinessMoney } from '../lib/format';
import { parseMoney } from '../lib/money';
import { quantityDifference, readQuantity } from '../lib/quantity';
import MoneyInput from './MoneyInput.vue';
import QuantityInput from './QuantityInput.vue';

type Product = OutputOf<'inventory.product.list'>['rows'][number];
export type StockAction = 'receive' | 'count' | 'write_off';

const props = defineProps<{ kind: StockAction; product: Product | null; units: readonly Unit[] }>();
const open = defineModel<boolean>('open', { default: false });

const { t, locale } = useT();
const business = useBusinessMoney();
const receive = useCommand('inventory.stock.receive');
const count = useCommand('inventory.stock.count');
const writeOff = useCommand('inventory.stock.write_off');
const command = computed(() => ({ receive, count, write_off: writeOff })[props.kind]);

const qty = ref('');
const cost = ref('');
const reason = ref('');
const tried = ref(false);

watch(
  open,
  (isOpen) => {
    if (!isOpen) return;
    qty.value = '';
    cost.value = '';
    reason.value = '';
    tried.value = false;
    for (const each of [receive, count, writeOff]) each.error.value = null;
  },
  { immediate: true },
);

const TEXTS = {
  receive: { title: 'inventory.stock.receiveTitle', qty: 'inventory.stock.receiveQty', submit: 'inventory.stock.receiveSubmit' },
  count: { title: 'inventory.stock.countTitle', qty: 'inventory.stock.countQty', submit: 'inventory.stock.countSubmit' },
  write_off: { title: 'inventory.stock.writeOffTitle', qty: 'inventory.stock.writeOffQty', submit: 'inventory.stock.writeOffSubmit' },
} as const;
const texts = computed(() => TEXTS[props.kind]);

const error = computed(() => command.value.error.value);
const pending = computed(() => command.value.pending.value);
const fields = computed(() => errorFields(error.value));
const step = computed(() => props.units.find((unit) => unit.code === props.product?.unit)?.increment);
const read = computed(() => readQuantity(qty.value));
const needsReason = computed(() => props.kind !== 'receive');

/** The count's difference, once the counted stock reads as a figure. */
const difference = computed(() => {
  if (props.kind !== 'count' || !props.product || !read.value.ok || read.value.value === null) return null;
  return quantityDifference(read.value.value, props.product.stock);
});

const NEEDS = {
  count: { qty: 'inventory.stock.countNeedsQty', reason: 'inventory.stock.countNeedsReason' },
  write_off: { qty: 'inventory.stock.writeOffNeedsQty', reason: 'inventory.stock.writeOffNeedsReason' },
} as const;

/** What is missing before the action can be taken (one thing at a time), or `''`. */
const needs = computed(() => {
  if (props.kind === 'receive') return '';
  if (!qty.value.trim()) return t(NEEDS[props.kind].qty);
  if (!reason.value.trim()) return t(NEEDS[props.kind].reason);
  return '';
});
const ready = computed(() => !!qty.value.trim() && (!needsReason.value || !!reason.value.trim()));

async function save(): Promise<void> {
  tried.value = true;
  const product = props.product;
  const quantity = read.value;
  const unitCost = parseMoney(cost.value, business.value);
  if (!product || !ready.value || !quantity.ok || quantity.value === null || !unitCost.ok) return;
  try {
    if (props.kind === 'receive') {
      await receive.run({ items: [{ product_id: product.id, qty: quantity.value, unit_cost: unitCost.cents }] });
    } else if (props.kind === 'count') {
      await count.run({ product_id: product.id, stock: quantity.value, reason: reason.value.trim() });
    } else {
      await writeOff.run({ product_id: product.id, qty: quantity.value, reason: reason.value.trim() });
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
    :title="$t(texts.title, { name: product?.name ?? '' })"
    testid="inventory-stock-form"
    :submit-label="$t(texts.submit)"
    :pending="pending"
    :error="error"
    :submit-disabled="!ready"
    @submit="save"
  >
    <div class="stock-form">
      <ion-list lines="full">
        <ion-item data-testid="inventory-stock-current">
          <ion-label>{{ $t('inventory.stock.current') }}</ion-label>
          <ion-note slot="end">
            {{ formatQuantity(product?.stock ?? '0', locale) }}
          </ion-note>
        </ion-item>
        <ion-item
          v-if="difference !== null"
          data-testid="inventory-stock-diff"
        >
          <ion-label>{{ $t('inventory.stock.countDiff') }}</ion-label>
          <ion-note
            slot="end"
            :color="difference.startsWith('-') ? 'danger' : 'success'"
          >
            {{ formatSignedQuantity(difference, locale) }}
          </ion-note>
        </ion-item>
      </ion-list>
      <QuantityInput
        v-model="qty"
        testid="inventory-stock-qty"
        :label="$t(texts.qty)"
        :unit="product?.unit"
        :step="step"
        :error-text="fields.qty ?? fields.stock"
        :show-error="tried"
      />
      <MoneyInput
        v-if="kind === 'receive'"
        v-model="cost"
        testid="inventory-stock-cost"
        :label="business ? $t('inventory.stock.receiveCostIn', { currency: business.currency }) : $t('inventory.stock.receiveCost')"
        :error-text="fields.unit_cost"
        :show-error="tried"
      />
      <ion-input
        v-if="needsReason"
        data-testid="inventory-stock-reason"
        :model-value="reason"
        :label="kind === 'count' ? $t('inventory.stock.countReason') : $t('inventory.stock.writeOffReason')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="500"
        :error-text="fields.reason"
        :class="{ 'ion-invalid': !!fields.reason, 'ion-touched': !!fields.reason }"
        @update:model-value="reason = $event === null || $event === undefined ? '' : String($event)"
      />
      <p
        v-if="needs"
        class="stock-form__needs"
        data-testid="inventory-stock-needs"
      >
        {{ needs }}
      </p>
    </div>
  </FormModal>
</template>

<style scoped>
.stock-form {
  display: grid;
  gap: 16px;
}

.stock-form__needs {
  margin: 0;
  text-align: center;
  font-size: 0.85rem;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
</style>
