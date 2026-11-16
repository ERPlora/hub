<script setup lang="ts">
// The open-price sheet (SALE-F09): the amount typed on the keypad, big on top; «Section (VAT)» with
// the business's departments (or Taxes' categories without any); «Add <amount>», which waits for both and for the
// business's money (hub#921: the amount is read in it, never before it answers; if that read fails it says so with
// «Retry», hub#938). It hands the line up in cents with its department (or tax category); the server names the line
// after it and the page writes it. A refusal (the permission, a department gone) is read here, over the button. Opens
// blank.
import { IonButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import BusinessMoneyError from '../../../../../base/frontend/components/BusinessMoneyError.vue';
import type { OpenLineIn } from '../../operations';
import { useTaxName } from '../../../../tax/frontend/composables/useTaxName';
import { useKeypadAmount } from '../../composables/pos/useKeypadAmount';
import { moneyDecimals } from '../../lib/format';
import DepartmentPicker, { type OpenPriceChoice } from './DepartmentPicker.vue';
import PosNumpad from './PosNumpad.vue';
import PosSheet from './PosSheet.vue';

defineProps<{ pending: boolean; error: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ add: [line: Pick<OpenLineIn, 'unit_price' | 'department_id' | 'tax_category_key'>] }>();

const taxName = useTaxName();
const typed = shallowRef('');
/** «Add» hands up `cents`, 0 until the business answers its money (so it waits in grey); `amount` is the figure. */
const { business, cents, shown: amount } = useKeypadAmount(typed);
const choice = shallowRef<OpenPriceChoice | null>(null);

watch(open, (isOpen) => {
  if (!isOpen) return;
  typed.value = '';
  choice.value = null;
});

const ready = computed(() => cents.value > 0 && !!choice.value);

function add(): void {
  const chosen = choice.value;
  if (!ready.value || !chosen) return;
  const charged = chosen.kind === 'department' ? { department_id: chosen.id } : { tax_category_key: chosen.key };
  emit('add', { unit_price: cents.value, ...charged });
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.openPrice')"
    testid="pos-open-price"
  >
    <template #top>
      <p
        class="pos-sheet-figure"
        data-testid="pos-open-price-amount"
      >
        {{ amount }}
      </p>
    </template>
    <PosNumpad
      v-model="typed"
      :decimals="moneyDecimals(business)"
    />
    <p
      class="pos-sheet-label"
      data-testid="pos-open-price-department-label"
    >
      {{ $t('sale.pos.department', { tax: taxName }) }}
    </p>
    <DepartmentPicker v-model="choice" />
    <template #foot>
      <div class="pos-sheet-foot">
        <BusinessMoneyError />
        <p
          v-if="error"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-open-price-error"
        >
          {{ error }}
        </p>
        <ion-button
          expand="block"
          class="pos-sheet-confirm"
          data-testid="pos-open-price-add"
          :disabled="!ready || pending"
          @click="add"
        >
          {{ $t('sale.pos.addAmount', { amount }) }}
        </ion-button>
      </div>
    </template>
  </PosSheet>
</template>
